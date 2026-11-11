#!/usr/bin/env python

"""OpenVPN configuration importer, profile manager, and tunnel control for BSD.

Implements an OpenVPN (.ovpn / .conf) parser and exporter modelled after
NetworkManager-openvpn (properties/import-export.c), adapted to FreeBSD and
GhostBSD (/usr/local/etc/openvpn). Supports inline and external certificates,
TLS / Password / TLS+Password / Static-Key authentication, tls-auth /
tls-crypt / tls-crypt-v2, ciphers, compression, proxies, and daemon lifecycle
management.
"""

from ipaddress import IPv4Address, IPv4Network, IPv6Interface, IPv6Network
import base64
import binascii
import os
import re
import shutil
import signal
import sys
import tempfile
from platform import system
from subprocess import DEVNULL, PIPE, run
from time import sleep

PREFIX = '/usr/local' if system() in ('FreeBSD', 'MidnightBSD', 'DragonFly') else sys.prefix
OPENVPN_CONFIG_PATH = f'{PREFIX}/etc/openvpn/'
OPENVPN_CERTS_PATH = f'{PREFIX}/etc/openvpn/certs/'
OPENVPN_PID_DIR = '/var/run'

OPENVPN_NOT_INSTALLED_MSG = (
    "OpenVPN is not installed on this system.\n\n"
    "Please install the openvpn package first "
    "(for example: sudo pkg install openvpn)."
)

# Safe identifier for filenames and rc/pid names.
PROFILE_ID_REGEX = re.compile(r'[^A-Za-z0-9_-]+')

INLINE_TAGS = (
    'ca',
    'cert',
    'key',
    'pkcs12',
    'tls-auth',
    'tls-crypt',
    'tls-crypt-v2',
    'secret',
    'extra-certs',
    'http-proxy-user-pass',
)

# Dangerous OpenVPN directives that execute external commands/plugins or
# write to arbitrary filesystem paths as root. Filtered out like NetworkManager-openvpn.
FORBIDDEN_OPENVPN_DIRECTIVES = frozenset({
    'script-security',
    'up',
    'down',
    'up-restart',
    'route-up',
    'route-pre-down',
    'ipchange',
    'client-connect',
    'client-disconnect',
    'learn-address',
    'auth-user-pass-verify',
    'tls-verify',
    'plugin',
    'management',
    'log',
    'log-append',
    'status',
    'writepid',
    'cd',
    'chroot',
    'daemon',
    'setenv',
    'setenv-safe',
    'lladdr',
})


def _clean_ovpn_val(value):
    """Strip newlines and NUL bytes to prevent OpenVPN directive injection."""
    return re.sub(r'[\r\n\x00]+', ' ', str(value or '')).strip()


def _is_safe_extra_line(raw_line):
    """Return True if an extra OpenVPN directive line is safe to preserve."""
    cleaned = _clean_ovpn_val(raw_line)
    if not cleaned:
        return False
    tokens = _tokenize_ovpn_line(cleaned)
    if not tokens:
        return False
    directive = tokens[0].lower().lstrip('-')
    return directive not in FORBIDDEN_OPENVPN_DIRECTIVES

CIPHER_OPTIONS = [
    '',
    'AES-256-GCM',
    'AES-128-GCM',
    'CHACHA20-POLY1305',
    'AES-256-CBC',
    'AES-192-CBC',
    'AES-128-CBC',
    'BF-CBC',
    'NONE',
]

AUTH_DIGEST_OPTIONS = [
    '',
    'SHA256',
    'SHA512',
    'SHA384',
    'SHA1',
    'MD5',
    'none',
]


def sanitize_profile_id(name):
    """Turn a display name or filename into a safe filesystem/daemon identifier.

    Args:
        name (str): raw connection name.

    Returns:
        str: sanitized identifier containing only ASCII letters, digits, '_' or '-'.
    """
    cleaned = PROFILE_ID_REGEX.sub('_', name.strip()).strip('_-')
    return cleaned or 'vpn'


def _openvpn_binary():
    """Locate the openvpn executable on BSD/Linux, or return None if not installed."""
    for candidate in (f'{PREFIX}/sbin/openvpn', '/usr/local/sbin/openvpn',
                      '/usr/sbin/openvpn', '/sbin/openvpn'):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which('openvpn')


def is_openvpn_installed():
    """Report whether the openvpn binary is available on this system."""
    return _openvpn_binary() is not None


def _normalize_ipv4_netmask(mask_or_prefix):
    """Convert a CIDR prefix ('24' or '/24') or dotted mask into a dotted IPv4 netmask."""
    val = str(mask_or_prefix).strip().lstrip('/')
    if not val:
        return '255.255.255.255'
    if val.isdigit():
        plen = int(val)
        if 0 <= plen <= 32:
            return str(IPv4Network(f'0.0.0.0/{plen}').netmask)
    try:
        return str(IPv4Address(val))
    except ValueError:
        return val


def detect_vpn_file_type(filepath):
    """Detect whether a configuration file is for WireGuard, IPsec/L2TP, or OpenVPN.

    Args:
        filepath (str): path to the .ovpn, .conf, .ipsec, or .sswan file.

    Returns:
        str: 'wireguard', 'ipsec', or 'openvpn'.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext in ('.sswan', '.ipsec'):
        return 'ipsec'

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as handle:
            content = handle.read(8192)
    except OSError:
        return 'openvpn'

    if re.search(r'^\s*\[Interface\]\s*$', content, re.MULTILINE | re.IGNORECASE) \
            and re.search(r'^\s*\[Peer\]\s*$', content, re.MULTILINE | re.IGNORECASE):
        return 'wireguard'
    if '# networkmgr-ipsec' in content:
        return 'ipsec'
    if re.search(r'(?m)^\s*conn\s+\S+', content) and re.search(
        r'(?m)^\s*(?:keyexchange|leftauth|rightauth|right|ike|esp)\s*=', content
    ):
        return 'ipsec'
    if content.lstrip().startswith('{') and '"remote"' in content and '"addr"' in content:
        return 'ipsec'
    return 'openvpn'


def _tokenize_ovpn_line(line):
    """Tokenize a single OpenVPN configuration line, honoring quotes and escapes.

    Follows the same rules as OpenVPN's parse_line() and NetworkManager-openvpn's
    args_next_line(): '#' and ';' start comments outside quotes, single and
    double quotes group tokens, and backslash escapes the next character.

    Args:
        line (str): raw line from configuration file.

    Returns:
        list[str]: parsed tokens, or empty list for blank/comment lines.
    """
    tokens = []
    current = []
    in_single = False
    in_double = False
    escaped = False

    for ch in line:
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == '\\' and not in_single:
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            continue
        if not in_single and not in_double:
            if ch in ('#', ';'):
                break
            if ch in (' ', '\t', '\r', '\n'):
                if current:
                    tokens.append(''.join(current))
                    current = []
                continue
        current.append(ch)

    if current:
        tokens.append(''.join(current))
    return tokens


def default_openvpn_config(name='openvpn'):
    """Return a fresh OpenVPN configuration dictionary with default settings.

    Args:
        name (str): connection display name.

    Returns:
        dict: structured OpenVPN configuration.
    """
    return {
        'vpn_type': 'openvpn',
        'name': name,
        'profile_id': sanitize_profile_id(name),
        'original_profile_id': None,
        'client': True,
        'remotes': [],
        'gateway': '',
        'port': '1194',
        'proto': 'udp',
        'dev': 'tun',
        'dev_type': '',
        'topology': '',
        'auth_type': 'tls',  # 'tls', 'password', 'tls-password', 'static-key'
        'ca_path': '',
        'ca_inline': '',
        'cert_path': '',
        'cert_inline': '',
        'key_path': '',
        'key_inline': '',
        'pkcs12_path': '',
        'pkcs12_inline': '',
        'extra_certs_path': '',
        'extra_certs_inline': '',
        'crl_verify_path': '',
        'tls_mode': 'none',  # 'none', 'tls-auth', 'tls-crypt', 'tls-crypt-v2'
        'tls_key_path': '',
        'tls_key_inline': '',
        'key_direction': '',
        'secret_path': '',
        'secret_inline': '',
        'secret_direction': '',
        'ipv4_method': 'auto',  # 'auto' or 'manual'
        'ifconfig_local': '',
        'ifconfig_remote': '',
        'route_gateway': '',
        'ipv6_method': 'auto',  # 'auto', 'manual', or 'disabled'
        'ifconfig_ipv6_local': '',
        'ifconfig_ipv6_prefix': '64',
        'ifconfig_ipv6_remote': '',
        'auth_user_pass': False,
        'auth_user_pass_path': '',
        'username': '',
        'password': '',
        'key_password': '',
        'askpass_path': '',
        'key_encrypted': False,
        'cipher': '',
        'data_ciphers': '',
        'data_ciphers_fallback': '',
        'auth': '',
        'remote_cert_tls': 'server',
        'verify_x509_name': '',
        'verify_x509_type': '',
        'tls_version_min': '',
        'tls_version_max': '',
        'tls_cipher': '',
        'tls_ciphersuites': '',
        'reneg_sec': '',
        'compress': '',
        'allow_compression': '',
        'tun_mtu': '',
        'fragment': '',
        'mssfix': '',
        'redirect_gateway': False,
        'redirect_gateway_flags': 'def1',
        'route_nopull': False,
        'routes': [],
        'routes_ipv6': [],
        'dns_servers': [],
        'search_domains': [],
        'nobind': True,
        'float': False,
        'persist_key': True,
        'persist_tun': True,
        'remote_random': False,
        'keepalive': '',
        'ping': '',
        'ping_restart': '',
        'ping_exit': '',
        'verb': '3',
        'proxy_type': 'none',  # 'none', 'http', 'socks'
        'proxy_server': '',
        'proxy_port': '',
        'proxy_username': '',
        'proxy_password': '',
        'extra_lines': [],
    }


def _resolve_relative_path(base_dir, file_ref):
    """Resolve a file reference relative to the .ovpn file's directory."""
    if not file_ref or file_ref == '[inline]':
        return ''
    if os.path.isabs(file_ref):
        return os.path.normpath(file_ref)
    candidate = os.path.normpath(os.path.join(base_dir, file_ref))
    return candidate


def _is_safe_credential_file(base_dir, filepath, is_internal_profile):
    """Check whether a credential/askpass file is safe to auto-read as root.

    Prevents an untrusted external .ovpn file from referencing /etc/master.passwd
    or symlinks via `auth-user-pass` / `askpass` and leaking contents into the UI.
    """
    if not filepath or os.path.islink(filepath) or not os.path.isfile(filepath):
        return False
    if is_internal_profile:
        return True
    try:
        real_base = os.path.realpath(base_dir)
        real_target = os.path.realpath(filepath)
        return os.path.commonpath([real_base, real_target]) == real_base
    except (ValueError, OSError):
        return False


def _key_content_is_encrypted(text):
    """Check whether PEM key content is encrypted."""
    return 'ENCRYPTED' in text or 'Proc-Type: 4,ENCRYPTED' in text


def _file_is_encrypted_key(filepath):
    """Check whether a key file on disk is an encrypted PEM private key."""
    if not filepath or not os.path.isfile(filepath):
        return False
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as handle:
            head = handle.read(2048)
        return _key_content_is_encrypted(head)
    except OSError:
        return False


def _read_credentials_file(filepath):
    """Read username and optional password from an OpenVPN auth-user-pass file."""
    if not filepath or not os.path.isfile(filepath):
        return '', ''
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as handle:
            lines = [ln.rstrip('\r\n') for ln in handle.readlines()]
        username = lines[0] if len(lines) >= 1 else ''
        password = lines[1] if len(lines) >= 2 else ''
        return username, password
    except OSError:
        return '', ''


def _read_single_line_file(filepath):
    """Read a single-line secret such as an askpass file."""
    if not filepath or not os.path.isfile(filepath):
        return ''
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as handle:
            return handle.readline().rstrip('\r\n')
    except OSError:
        return ''


def parse_openvpn_config(filepath):
    """Parse an OpenVPN (.ovpn / .conf) file like NetworkManager-openvpn.

    Extracts all connection parameters, inline certificates/keys, file
    paths (resolved relative to the imported file's directory), authentication
    mode, TLS settings, ciphers, proxies, routes, and preserves any extra
    directives.

    Args:
        filepath (str): path to the .ovpn or .conf file.

    Returns:
        dict: structured OpenVPN configuration dictionary.

    Raises:
        ValueError: if the file cannot be read or contains no usable OpenVPN
            directives.
    """
    if not os.path.isfile(filepath):
        raise ValueError(f'File not found: "{filepath}"')

    base_dir = os.path.dirname(os.path.abspath(filepath))
    stem = os.path.splitext(os.path.basename(filepath))[0]
    cfg = default_openvpn_config(stem)
    is_internal_profile = False
    # If the file being loaded is already inside OPENVPN_CONFIG_PATH, record its
    # original_profile_id so renaming it in the editor cleans up the old file.
    if os.path.exists(OPENVPN_CONFIG_PATH):
        try:
            if os.path.samefile(base_dir, OPENVPN_CONFIG_PATH):
                cfg['original_profile_id'] = stem
                is_internal_profile = True
        except OSError:
            pass
    # Reset defaults that should reflect the file's explicit contents
    cfg['remote_cert_tls'] = ''
    cfg['nobind'] = False
    cfg['persist_key'] = False
    cfg['persist_tun'] = False

    try:
        with open(filepath, 'r', encoding='utf-8-sig', errors='replace') as handle:
            raw_lines = handle.readlines()
    except OSError as exc:
        raise ValueError(f'Could not read "{filepath}": {exc}') from exc

    active_tag = None
    tag_buffer = []
    in_connection_block = False

    for raw_line in raw_lines:
        stripped = raw_line.strip()

        # Preserve display name header if written by NetworkMgr
        if active_tag is None and stripped.startswith('# Name ='):
            custom_name = stripped.split('=', 1)[1].strip()
            if custom_name:
                cfg['name'] = custom_name
            continue

        # Handle closing of an inline block
        if active_tag is not None:
            if stripped.lower() == f'</{active_tag}>':
                content = ''.join(tag_buffer).strip()
                if active_tag == 'ca':
                    cfg['ca_inline'] = content
                elif active_tag == 'cert':
                    cfg['cert_inline'] = content
                elif active_tag == 'key':
                    cfg['key_inline'] = content
                    if _key_content_is_encrypted(content):
                        cfg['key_encrypted'] = True
                elif active_tag == 'pkcs12':
                    cfg['pkcs12_inline'] = content
                elif active_tag in ('tls-auth', 'tls-crypt', 'tls-crypt-v2'):
                    cfg['tls_mode'] = active_tag
                    cfg['tls_key_inline'] = content
                elif active_tag == 'secret':
                    cfg['secret_inline'] = content
                elif active_tag == 'extra-certs':
                    cfg['extra_certs_inline'] = content
                elif active_tag == 'http-proxy-user-pass':
                    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
                    if len(lines) >= 1:
                        cfg['proxy_username'] = lines[0]
                    if len(lines) >= 2:
                        cfg['proxy_password'] = lines[1]
                active_tag = None
                tag_buffer = []
            else:
                tag_buffer.append(raw_line)
            continue

        # Handle <connection> wrapper block (inner lines are regular directives)
        if stripped.lower() == '<connection>':
            in_connection_block = True
            continue
        if stripped.lower() == '</connection>':
            in_connection_block = False
            continue

        # Check for opening of an inline block: <ca>, <cert>, <key>, etc.
        tag_match = re.match(r'^<([a-zA-Z0-9_-]+)>\s*$', stripped)
        if tag_match and tag_match.group(1).lower() in INLINE_TAGS:
            active_tag = tag_match.group(1).lower()
            tag_buffer = []
            continue

        tokens = _tokenize_ovpn_line(raw_line)
        if not tokens:
            continue

        directive = tokens[0].lower()
        args = tokens[1:]

        if directive in ('client', 'pull', 'tls-client'):
            cfg['client'] = True
        elif directive == 'remote' and len(args) >= 1:
            host = args[0]
            port = args[1] if len(args) >= 2 else ''
            proto = args[2].lower() if len(args) >= 3 else ''
            cfg['remotes'].append({'host': host, 'port': port, 'proto': proto})
        elif directive in ('port', 'rport') and len(args) >= 1:
            cfg['port'] = args[0]
        elif directive == 'proto' and len(args) >= 1:
            p = args[0].lower()
            if p.startswith('tcp'):
                cfg['proto'] = 'tcp'
            else:
                cfg['proto'] = 'udp'
        elif directive == 'dev' and len(args) >= 1:
            cfg['dev'] = args[0]
        elif directive == 'dev-type' and len(args) >= 1:
            cfg['dev_type'] = args[0].lower()
        elif directive == 'topology' and len(args) >= 1:
            cfg['topology'] = args[0].lower()
        elif directive == 'ca' and len(args) >= 1:
            if args[0] != '[inline]':
                cfg['ca_path'] = _resolve_relative_path(base_dir, args[0])
        elif directive == 'cert' and len(args) >= 1:
            if args[0] != '[inline]':
                cfg['cert_path'] = _resolve_relative_path(base_dir, args[0])
        elif directive == 'key' and len(args) >= 1:
            if args[0] != '[inline]':
                cfg['key_path'] = _resolve_relative_path(base_dir, args[0])
                if _file_is_encrypted_key(cfg['key_path']):
                    cfg['key_encrypted'] = True
        elif directive == 'pkcs12' and len(args) >= 1:
            if args[0] != '[inline]':
                cfg['pkcs12_path'] = _resolve_relative_path(base_dir, args[0])
        elif directive == 'extra-certs' and len(args) >= 1:
            if args[0] != '[inline]':
                cfg['extra_certs_path'] = _resolve_relative_path(base_dir, args[0])
        elif directive == 'crl-verify' and len(args) >= 1:
            cfg['crl_verify_path'] = _resolve_relative_path(base_dir, args[0])
        elif directive == 'tls-auth' and len(args) >= 1:
            cfg['tls_mode'] = 'tls-auth'
            if args[0] != '[inline]':
                cfg['tls_key_path'] = _resolve_relative_path(base_dir, args[0])
            if len(args) >= 2 and args[1] in ('0', '1', 'bidirectional'):
                cfg['key_direction'] = args[1]
        elif directive in ('tls-crypt', 'tls-crypt-v2') and len(args) >= 1:
            cfg['tls_mode'] = directive
            if args[0] != '[inline]':
                cfg['tls_key_path'] = _resolve_relative_path(base_dir, args[0])
        elif directive == 'key-direction' and len(args) >= 1:
            if args[0] in ('0', '1', 'bidirectional'):
                cfg['key_direction'] = args[0]
        elif directive == 'secret' and len(args) >= 1:
            if args[0] != '[inline]':
                cfg['secret_path'] = _resolve_relative_path(base_dir, args[0])
            if len(args) >= 2 and args[1] in ('0', '1'):
                cfg['secret_direction'] = args[1]
        elif directive == 'ifconfig' and len(args) >= 2:
            cfg['ipv4_method'] = 'manual'
            cfg['ifconfig_local'] = args[0]
            cfg['ifconfig_remote'] = args[1]
        elif directive == 'route-gateway' and len(args) >= 1:
            cfg['route_gateway'] = args[0]
        elif directive == 'ifconfig-ipv6' and len(args) >= 1:
            cfg['ipv6_method'] = 'manual'
            addr_part = args[0]
            if '/' in addr_part:
                loc6, plen6 = addr_part.split('/', 1)
                cfg['ifconfig_ipv6_local'] = loc6.strip()
                cfg['ifconfig_ipv6_prefix'] = plen6.strip() or '64'
            else:
                cfg['ifconfig_ipv6_local'] = addr_part.strip()
            if len(args) >= 2:
                cfg['ifconfig_ipv6_remote'] = args[1].strip()
        elif directive == 'pull-filter' and len(args) >= 2:
            if args[0].lower() == 'ignore' and 'ipv6' in args[1].lower():
                cfg['ipv6_method'] = 'disabled'
            elif _is_safe_extra_line(raw_line):
                cfg['extra_lines'].append(_clean_ovpn_val(raw_line))
        elif directive == 'auth-user-pass':
            cfg['auth_user_pass'] = True
            if len(args) >= 1 and args[0] != '[inline]':
                resolved = _resolve_relative_path(base_dir, args[0])
                if _is_safe_credential_file(base_dir, resolved, is_internal_profile):
                    cfg['auth_user_pass_path'] = resolved
                    user, pwd = _read_credentials_file(resolved)
                    if user:
                        cfg['username'] = user
                    if pwd:
                        cfg['password'] = pwd
        elif directive == 'askpass' and len(args) >= 1:
            resolved = _resolve_relative_path(base_dir, args[0])
            if _is_safe_credential_file(base_dir, resolved, is_internal_profile):
                cfg['askpass_path'] = resolved
                key_pwd = _read_single_line_file(resolved)
                if key_pwd:
                    cfg['key_password'] = key_pwd
        elif directive == 'cipher' and len(args) >= 1:
            cfg['cipher'] = args[0]
        elif directive == 'data-ciphers' and len(args) >= 1:
            cfg['data_ciphers'] = args[0]
        elif directive == 'data-ciphers-fallback' and len(args) >= 1:
            cfg['data_ciphers_fallback'] = args[0]
        elif directive == 'auth' and len(args) >= 1:
            cfg['auth'] = args[0]
        elif directive in ('remote-cert-tls', 'ns-cert-type') and len(args) >= 1:
            cfg['remote_cert_tls'] = args[0].lower()
        elif directive == 'verify-x509-name' and len(args) >= 1:
            cfg['verify_x509_name'] = args[0]
            cfg['verify_x509_type'] = args[1] if len(args) >= 2 else ''
        elif directive == 'tls-version-min' and len(args) >= 1:
            cfg['tls_version_min'] = args[0]
        elif directive == 'tls-version-max' and len(args) >= 1:
            cfg['tls_version_max'] = args[0]
        elif directive == 'tls-cipher' and len(args) >= 1:
            cfg['tls_cipher'] = args[0]
        elif directive == 'tls-ciphersuites' and len(args) >= 1:
            cfg['tls_ciphersuites'] = args[0]
        elif directive == 'reneg-sec' and len(args) >= 1:
            cfg['reneg_sec'] = args[0]
        elif directive == 'compress':
            cfg['compress'] = args[0] if args else 'stub-v2'
        elif directive == 'comp-lzo':
            mode = args[0].lower() if args else 'adaptive'
            cfg['compress'] = f'comp-lzo-{mode}'
        elif directive == 'allow-compression' and len(args) >= 1:
            cfg['allow_compression'] = args[0].lower()
        elif directive == 'tun-mtu' and len(args) >= 1:
            cfg['tun_mtu'] = args[0]
        elif directive == 'fragment' and len(args) >= 1:
            cfg['fragment'] = args[0]
        elif directive == 'mssfix':
            cfg['mssfix'] = args[0] if args else 'yes'
        elif directive == 'redirect-gateway':
            cfg['redirect_gateway'] = True
            cfg['redirect_gateway_flags'] = ' '.join(args) if args else 'def1'
        elif directive == 'route-nopull':
            cfg['route_nopull'] = True
        elif directive == 'route' and len(args) >= 1:
            net_arg = args[0]
            mask_arg = args[1] if len(args) >= 2 else '255.255.255.255'
            if '/' in net_arg and len(args) == 1:
                net_part, plen_part = net_arg.split('/', 1)
                net_arg = net_part
                mask_arg = _normalize_ipv4_netmask(plen_part)
            else:
                mask_arg = _normalize_ipv4_netmask(mask_arg)
            cfg['routes'].append({
                'network': net_arg,
                'netmask': mask_arg,
                'gateway': args[2] if len(args) >= 3 else 'vpn_gateway',
                'metric': args[3] if len(args) >= 4 else '',
            })
        elif directive == 'route-ipv6' and len(args) >= 1:
            cfg['routes_ipv6'].append({
                'network': args[0],
                'gateway': args[1] if len(args) >= 2 else '',
                'metric': args[2] if len(args) >= 3 else '',
            })
        elif directive == 'dhcp-option' and len(args) >= 2:
            opt_kind = args[0].upper()
            if opt_kind == 'DNS':
                cfg['dns_servers'].append(args[1])
            elif opt_kind in ('DOMAIN', 'DOMAIN-SEARCH'):
                cfg['search_domains'].append(args[1])
            else:
                cfg['extra_lines'].append(raw_line.rstrip('\r\n'))
        elif directive == 'nobind':
            cfg['nobind'] = True
        elif directive == 'float':
            cfg['float'] = True
        elif directive == 'persist-key':
            cfg['persist_key'] = True
        elif directive == 'persist-tun':
            cfg['persist_tun'] = True
        elif directive == 'remote-random':
            cfg['remote_random'] = True
        elif directive == 'keepalive' and len(args) >= 2:
            cfg['keepalive'] = f'{args[0]} {args[1]}'
        elif directive == 'ping' and len(args) >= 1:
            cfg['ping'] = args[0]
        elif directive == 'ping-restart' and len(args) >= 1:
            cfg['ping_restart'] = args[0]
        elif directive == 'ping-exit' and len(args) >= 1:
            cfg['ping_exit'] = args[0]
        elif directive == 'verb' and len(args) >= 1:
            cfg['verb'] = args[0]
        elif directive == 'http-proxy' and len(args) >= 2:
            cfg['proxy_type'] = 'http'
            cfg['proxy_server'] = args[0]
            cfg['proxy_port'] = args[1]
            if len(args) >= 3 and args[2] not in ('auto', 'auto-nct', 'none'):
                auth_file = _resolve_relative_path(base_dir, args[2])
                if _is_safe_credential_file(base_dir, auth_file, is_internal_profile):
                    p_user, p_pwd = _read_credentials_file(auth_file)
                    if p_user:
                        cfg['proxy_username'] = p_user
                    if p_pwd:
                        cfg['proxy_password'] = p_pwd
        elif directive == 'socks-proxy' and len(args) >= 1:
            cfg['proxy_type'] = 'socks'
            cfg['proxy_server'] = args[0]
            cfg['proxy_port'] = args[1] if len(args) >= 2 else '1080'
        elif directive in FORBIDDEN_OPENVPN_DIRECTIVES:
            # Disallow script execution and arbitrary file-write directives
            continue
        else:
            if _is_safe_extra_line(raw_line):
                cfg['extra_lines'].append(_clean_ovpn_val(raw_line))

    # Format the Gateway string the same way NetworkManager-openvpn does:
    # host[:port[:proto]], comma-separated when multiple remotes exist.
    gw_parts = []
    for rem in cfg['remotes']:
        entry = rem['host']
        if rem['port'] and rem['proto']:
            entry = f"{rem['host']}:{rem['port']}:{rem['proto']}"
        elif rem['port']:
            entry = f"{rem['host']}:{rem['port']}"
        gw_parts.append(entry)
    cfg['gateway'] = ', '.join(gw_parts)

    if cfg['remotes']:
        first_remote = cfg['remotes'][0]
        if first_remote['port']:
            cfg['port'] = first_remote['port']
        if first_remote['proto']:
            cfg['proto'] = 'tcp' if first_remote['proto'].startswith('tcp') else 'udp'

    # Determine Authentication Type identically to NetworkManager-openvpn
    has_secret = bool(cfg['secret_path'] or cfg['secret_inline'])
    has_client_cert = bool(
        cfg['cert_path'] or cfg['cert_inline']
        or cfg['pkcs12_path'] or cfg['pkcs12_inline']
    )
    has_user_pass = bool(cfg['auth_user_pass'])

    if has_secret and not has_client_cert and not has_user_pass:
        cfg['auth_type'] = 'static-key'
    elif has_client_cert and has_user_pass:
        cfg['auth_type'] = 'tls-password'
    elif has_user_pass and not has_client_cert:
        cfg['auth_type'] = 'password'
    else:
        cfg['auth_type'] = 'tls'

    # Fill sensible defaults if missing
    if not cfg['cipher'] and cfg['data_ciphers']:
        first_cipher = cfg['data_ciphers'].split(':')[0].strip()
        if first_cipher:
            cfg['cipher'] = first_cipher

    return cfg


def _write_secure_file(path, content, mode=0o600):
    """Write text to a file atomically with strict permissions and no symlink following."""
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    if os.path.islink(path):
        raise ValueError(f'Refusing to write to symlink: {path}')
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, mode)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        handle.write(content.rstrip('\n') + '\n')
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _write_secure_bytes(path, data, mode=0o600):
    """Write binary bytes to a file with strict permissions and no symlink following."""
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    if os.path.islink(path):
        raise ValueError(f'Refusing to write to symlink: {path}')
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, mode)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _copy_or_keep_cert(src_path, dest_dir, dest_filename, mode=0o600):
    """Copy an external certificate/key into the profile's cert directory."""
    if not src_path:
        return ''
    if os.path.islink(src_path):
        raise ValueError(f'Refusing to import symlinked certificate/key: "{src_path}"')
    os.makedirs(dest_dir, exist_ok=True)
    os.chmod(dest_dir, 0o700)
    dest_path = os.path.join(dest_dir, dest_filename)
    if os.path.islink(dest_path):
        raise ValueError(f'Refusing to overwrite symlink: "{dest_path}"')
    if os.path.abspath(src_path) != os.path.abspath(dest_path) and os.path.isfile(src_path):
        with open(src_path, 'rb') as src_fh:
            data = src_fh.read()
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(dest_path, flags, 0o600)
        with os.fdopen(fd, 'wb') as dst_fh:
            dst_fh.write(data)
        os.chmod(dest_path, 0o600)
        return dest_path
    return src_path


def _parse_gateway_string(gateway_text, default_port, default_proto):
    """Parse NetworkManager-style gateway string ('host[:port[:proto]], ...')."""
    remotes = []
    for chunk in re.split(r'[,\s]+', gateway_text.strip()):
        if not chunk:
            continue
        # Handle IPv6 [addr]:port:proto or standard host:port:proto
        if chunk.startswith('['):
            match = re.match(r'^\[([^\]]+)\](?::(\d+))?(?::(udp|tcp|udp4|udp6|tcp4|tcp6))?$',
                             chunk, re.IGNORECASE)
            if match:
                remotes.append({
                    'host': match.group(1),
                    'port': match.group(2) or default_port,
                    'proto': (match.group(3) or default_proto).lower(),
                })
                continue
        parts = chunk.split(':')
        host = parts[0].strip()
        port = parts[1].strip() if len(parts) >= 2 and parts[1].strip() else default_port
        proto = parts[2].strip().lower() if len(parts) >= 3 and parts[2].strip() else ''
        remotes.append({'host': host, 'port': port, 'proto': proto})
    return remotes


def save_openvpn_config(cfg):
    """Save an OpenVPN configuration and its certificates to /usr/local/etc/openvpn/.

    Extracts inline certificates/keys or copies referenced certificate files
    into /usr/local/etc/openvpn/certs/<profile_id>/ with strict permissions
    (0600 for keys and credentials, 0644 for public certificates), and writes
    the complete OpenVPN configuration to /usr/local/etc/openvpn/<profile_id>.conf.

    Args:
        cfg (dict): structured OpenVPN configuration dictionary.

    Returns:
        str: the saved profile_id.

    Raises:
        ValueError: if required fields (such as Name or Gateway) are missing.
    """
    display_name = cfg.get('name', '').strip()
    if not display_name:
        raise ValueError('Connection name is required.')

    profile_id = sanitize_profile_id(display_name)
    original_id = cfg.get('original_profile_id')
    gateway = cfg.get('gateway', '').strip()
    if not gateway and not cfg.get('remotes'):
        raise ValueError('Gateway (remote server address) is required.')

    port = str(cfg.get('port', '1194')).strip() or '1194'
    proto = cfg.get('proto', 'udp').strip().lower() or 'udp'
    remotes = _parse_gateway_string(gateway, port, proto) if gateway else cfg['remotes']
    if not remotes:
        raise ValueError('At least one valid remote gateway is required.')

    os.makedirs(OPENVPN_CONFIG_PATH, exist_ok=True)
    cert_dir = os.path.join(OPENVPN_CERTS_PATH, profile_id)
    os.makedirs(cert_dir, exist_ok=True)
    os.chmod(cert_dir, 0o700)

    # Materialize inline certs/keys or copy external ones into cert_dir
    ca_file = ''
    if cfg.get('ca_inline'):
        ca_file = os.path.join(cert_dir, 'ca.crt')
        _write_secure_file(ca_file, cfg['ca_inline'], 0o644)
    elif cfg.get('ca_path'):
        ca_file = _copy_or_keep_cert(cfg['ca_path'], cert_dir, 'ca.crt', 0o644)

    cert_file = ''
    if cfg.get('cert_inline'):
        cert_file = os.path.join(cert_dir, 'client.crt')
        _write_secure_file(cert_file, cfg['cert_inline'], 0o644)
    elif cfg.get('cert_path'):
        cert_file = _copy_or_keep_cert(cfg['cert_path'], cert_dir, 'client.crt', 0o644)

    key_file = ''
    if cfg.get('key_inline'):
        key_file = os.path.join(cert_dir, 'client.key')
        _write_secure_file(key_file, cfg['key_inline'], 0o600)
    elif cfg.get('key_path'):
        key_file = _copy_or_keep_cert(cfg['key_path'], cert_dir, 'client.key', 0o600)

    pkcs12_file = ''
    if cfg.get('pkcs12_inline'):
        pkcs12_file = os.path.join(cert_dir, 'client.p12')
        raw_p12 = cfg['pkcs12_inline']
        if isinstance(raw_p12, bytes):
            _write_secure_bytes(pkcs12_file, raw_p12, 0o600)
        else:
            try:
                p12_bytes = base64.b64decode(raw_p12.strip(), validate=True)
                _write_secure_bytes(pkcs12_file, p12_bytes, 0o600)
            except (binascii.Error, ValueError):
                try:
                    p12_bytes = base64.b64decode(raw_p12.strip(), validate=False)
                    if p12_bytes:
                        _write_secure_bytes(pkcs12_file, p12_bytes, 0o600)
                    else:
                        _write_secure_file(pkcs12_file, raw_p12, 0o600)
                except (binascii.Error, ValueError):
                    _write_secure_file(pkcs12_file, raw_p12, 0o600)
    elif cfg.get('pkcs12_path'):
        pkcs12_file = _copy_or_keep_cert(cfg['pkcs12_path'], cert_dir, 'client.p12', 0o600)

    extra_certs_file = ''
    if cfg.get('extra_certs_inline'):
        extra_certs_file = os.path.join(cert_dir, 'extra-certs.pem')
        _write_secure_file(extra_certs_file, cfg['extra_certs_inline'], 0o644)
    elif cfg.get('extra_certs_path'):
        extra_certs_file = _copy_or_keep_cert(
            cfg['extra_certs_path'], cert_dir, 'extra-certs.pem', 0o644
        )

    tls_key_file = ''
    tls_mode = cfg.get('tls_mode', 'none')
    if tls_mode in ('tls-auth', 'tls-crypt', 'tls-crypt-v2'):
        if cfg.get('tls_key_inline'):
            tls_key_file = os.path.join(cert_dir, 'ta.key')
            _write_secure_file(tls_key_file, cfg['tls_key_inline'], 0o600)
        elif cfg.get('tls_key_path'):
            tls_key_file = _copy_or_keep_cert(cfg['tls_key_path'], cert_dir, 'ta.key', 0o600)

    secret_file = ''
    if cfg.get('secret_inline'):
        secret_file = os.path.join(cert_dir, 'static.key')
        _write_secure_file(secret_file, cfg['secret_inline'], 0o600)
    elif cfg.get('secret_path'):
        secret_file = _copy_or_keep_cert(cfg['secret_path'], cert_dir, 'static.key', 0o600)

    # Assemble the OpenVPN configuration file
    lines = [
        f'# Name = {display_name}',
        '# Generated by NetworkMgr',
    ]

    auth_type = cfg.get('auth_type', 'tls')
    if auth_type != 'static-key':
        lines.append('client')

    dev = cfg.get('dev', 'tun').strip() or 'tun'
    lines.append(f'dev {dev}')
    if cfg.get('dev_type'):
        lines.append(f"dev-type {cfg['dev_type']}")
    if cfg.get('topology'):
        lines.append(f"topology {cfg['topology']}")

    lines.append(f'proto {proto}')

    for rem in remotes:
        r_host = rem['host']
        r_port = rem.get('port') or port
        r_proto = rem.get('proto')
        if r_proto and r_proto != proto:
            lines.append(f'remote {r_host} {r_port} {r_proto}')
        elif r_port:
            lines.append(f'remote {r_host} {r_port}')
        else:
            lines.append(f'remote {r_host}')

    if cfg.get('remote_random'):
        lines.append('remote-random')
    if cfg.get('nobind', True):
        lines.append('nobind')
    if cfg.get('float'):
        lines.append('float')
    if cfg.get('persist_key', True):
        lines.append('persist-key')
    if cfg.get('persist_tun', True):
        lines.append('persist-tun')

    # Certificates & Authentication
    if auth_type == 'static-key':
        if secret_file:
            if cfg.get('secret_direction') in ('0', '1'):
                lines.append(f"secret {secret_file} {cfg['secret_direction']}")
            else:
                lines.append(f'secret {secret_file}')
        if cfg.get('ifconfig_local') and cfg.get('ifconfig_remote'):
            lines.append(f"ifconfig {cfg['ifconfig_local']} {cfg['ifconfig_remote']}")
    else:
        if pkcs12_file:
            lines.append(f'pkcs12 {pkcs12_file}')
        else:
            if ca_file:
                lines.append(f'ca {ca_file}')
            if auth_type in ('tls', 'tls-password'):
                if cert_file:
                    lines.append(f'cert {cert_file}')
                if key_file:
                    lines.append(f'key {key_file}')
        if extra_certs_file:
            lines.append(f'extra-certs {extra_certs_file}')
        if cfg.get('crl_verify_path'):
            lines.append(f"crl-verify {cfg['crl_verify_path']}")
        if cfg.get('ipv4_method') == 'manual' and cfg.get('ifconfig_local'):
            remote_or_mask = _normalize_ipv4_netmask(
                cfg.get('ifconfig_remote') or '255.255.255.0'
            )
            lines.append(f"ifconfig {cfg['ifconfig_local'].strip()} {remote_or_mask}")
        if cfg.get('route_gateway', '').strip():
            lines.append(f"route-gateway {cfg['route_gateway'].strip()}")

    # IPv6 configuration
    ipv6_method = cfg.get('ipv6_method', 'auto')
    if ipv6_method == 'manual' and cfg.get('ifconfig_ipv6_local', '').strip():
        loc6 = cfg['ifconfig_ipv6_local'].strip()
        plen6 = str(cfg.get('ifconfig_ipv6_prefix', '64')).strip().lstrip('/') or '64'
        if '/' not in loc6:
            loc6 = f'{loc6}/{plen6}'
        rem6 = cfg.get('ifconfig_ipv6_remote', '').strip()
        if rem6:
            lines.append(f'ifconfig-ipv6 {loc6} {rem6}')
        else:
            lines.append(f'ifconfig-ipv6 {loc6}')
    elif ipv6_method == 'disabled':
        lines.append('pull-filter ignore "ifconfig-ipv6 "')
        lines.append('pull-filter ignore "route-ipv6 "')

    # Private key password (askpass)
    key_password = cfg.get('key_password', '')
    askpass_file = os.path.join(cert_dir, 'askpass.txt')
    if key_password:
        _write_secure_file(askpass_file, key_password, 0o600)
        lines.append(f'askpass {askpass_file}')
    elif os.path.exists(askpass_file):
        os.remove(askpass_file)

    # Username / Password authentication
    auth_file = os.path.join(cert_dir, 'auth.txt')
    if auth_type in ('password', 'tls-password') or cfg.get('auth_user_pass'):
        username = cfg.get('username', '').strip()
        password = cfg.get('password', '')
        if username and password:
            _write_secure_file(auth_file, f'{username}\n{password}', 0o600)
            lines.append(f'auth-user-pass {auth_file}')
        elif username:
            # Store username; password will be requested on connect
            _write_secure_file(auth_file, f'{username}', 0o600)
            lines.append(f'auth-user-pass {auth_file}')
        else:
            if os.path.exists(auth_file):
                os.remove(auth_file)
            lines.append('auth-user-pass')
    elif os.path.exists(auth_file):
        os.remove(auth_file)

    # TLS-Auth / TLS-Crypt
    if tls_mode == 'tls-auth' and tls_key_file:
        key_dir = cfg.get('key_direction', '').strip()
        if key_dir in ('0', '1'):
            lines.append(f'tls-auth {tls_key_file} {key_dir}')
            lines.append(f'key-direction {key_dir}')
        else:
            lines.append(f'tls-auth {tls_key_file}')
    elif tls_mode in ('tls-crypt', 'tls-crypt-v2') and tls_key_file:
        lines.append(f'{tls_mode} {tls_key_file}')

    # Security / Ciphers / Digests
    if cfg.get('cipher'):
        lines.append(f"cipher {cfg['cipher']}")
    if cfg.get('data_ciphers'):
        lines.append(f"data-ciphers {cfg['data_ciphers']}")
    if cfg.get('data_ciphers_fallback'):
        lines.append(f"data-ciphers-fallback {cfg['data_ciphers_fallback']}")
    if cfg.get('auth'):
        lines.append(f"auth {cfg['auth']}")

    if cfg.get('remote_cert_tls') in ('server', 'client'):
        lines.append(f"remote-cert-tls {cfg['remote_cert_tls']}")
    if cfg.get('verify_x509_name'):
        v_name = _clean_ovpn_val(cfg['verify_x509_name']).replace('\\', '\\\\').replace('"', '\\"')
        v_type = _clean_ovpn_val(cfg.get('verify_x509_type', ''))
        if v_type in ('name', 'name-prefix', 'subject'):
            lines.append(f'verify-x509-name "{v_name}" {v_type}')
        else:
            lines.append(f'verify-x509-name "{v_name}"')
    if cfg.get('tls_version_min'):
        lines.append(f"tls-version-min {cfg['tls_version_min']}")
    if cfg.get('tls_version_max'):
        lines.append(f"tls-version-max {cfg['tls_version_max']}")
    if cfg.get('tls_cipher'):
        lines.append(f"tls-cipher {cfg['tls_cipher']}")
    if cfg.get('tls_ciphersuites'):
        lines.append(f"tls-ciphersuites {cfg['tls_ciphersuites']}")
    if cfg.get('reneg_sec'):
        lines.append(f"reneg-sec {cfg['reneg_sec']}")

    # Compression
    comp = cfg.get('compress', '').strip()
    if comp.startswith('comp-lzo-'):
        lzo_mode = comp.replace('comp-lzo-', '')
        lines.append(f'comp-lzo {lzo_mode}')
    elif comp:
        lines.append(f'compress {comp}')
    if cfg.get('allow_compression'):
        lines.append(f"allow-compression {cfg['allow_compression']}")

    # Tunnel / MTU / Routing
    if cfg.get('tun_mtu'):
        lines.append(f"tun-mtu {cfg['tun_mtu']}")
    if cfg.get('fragment'):
        lines.append(f"fragment {cfg['fragment']}")
    if cfg.get('mssfix'):
        mss_val = str(cfg['mssfix']).strip()
        if mss_val in ('True', 'yes'):
            lines.append('mssfix')
        elif mss_val not in ('False', 'no', ''):
            lines.append(f'mssfix {mss_val}')

    if cfg.get('redirect_gateway'):
        flags = cfg.get('redirect_gateway_flags', 'def1').strip()
        lines.append(f'redirect-gateway {flags}' if flags else 'redirect-gateway def1')
    if cfg.get('route_nopull'):
        lines.append('route-nopull')
    for rt in cfg.get('routes', []):
        net = rt.get('network', '').strip()
        if net:
            if '/' in net and not rt.get('netmask', '').strip():
                net_part, plen_part = net.split('/', 1)
                net = net_part.strip()
                mask = _normalize_ipv4_netmask(plen_part)
            else:
                mask = _normalize_ipv4_netmask(rt.get('netmask') or '255.255.255.255')
            gw = rt.get('gateway', '').strip() or 'vpn_gateway'
            metric = rt.get('metric', '').strip()
            lines.append(f'route {net} {mask} {gw} {metric}'.strip())

    for rt6 in cfg.get('routes_ipv6', []):
        net6 = rt6.get('network', '').strip()
        if net6:
            if '/' not in net6:
                net6 = f'{net6}/128'
            gw6 = rt6.get('gateway', '').strip()
            metric6 = rt6.get('metric', '').strip()
            if gw6 and metric6:
                lines.append(f'route-ipv6 {net6} {gw6} {metric6}')
            elif gw6:
                lines.append(f'route-ipv6 {net6} {gw6}')
            else:
                lines.append(f'route-ipv6 {net6}')

    for dns in cfg.get('dns_servers', []):
        if dns.strip():
            lines.append(f'dhcp-option DNS {dns.strip()}')
    for dom in cfg.get('search_domains', []):
        if dom.strip():
            lines.append(f'dhcp-option DOMAIN {dom.strip()}')

    # Keepalive / Ping
    if cfg.get('keepalive'):
        lines.append(f"keepalive {cfg['keepalive']}")
    else:
        if cfg.get('ping'):
            lines.append(f"ping {cfg['ping']}")
        if cfg.get('ping_restart'):
            lines.append(f"ping-restart {cfg['ping_restart']}")
        if cfg.get('ping_exit'):
            lines.append(f"ping-exit {cfg['ping_exit']}")

    # Proxy
    proxy_type = cfg.get('proxy_type', 'none')
    proxy_srv = cfg.get('proxy_server', '').strip()
    proxy_prt = cfg.get('proxy_port', '').strip()
    if proxy_type == 'http' and proxy_srv and proxy_prt:
        if cfg.get('proxy_username'):
            proxy_auth_file = os.path.join(cert_dir, 'proxy-auth.txt')
            _write_secure_file(
                proxy_auth_file,
                f"{cfg['proxy_username']}\n{cfg.get('proxy_password', '')}",
                0o600
            )
            lines.append(f'http-proxy {proxy_srv} {proxy_prt} {proxy_auth_file}')
        else:
            lines.append(f'http-proxy {proxy_srv} {proxy_prt}')
    elif proxy_type == 'socks' and proxy_srv:
        lines.append(f"socks-proxy {proxy_srv} {proxy_prt or '1080'}")

    verb = str(cfg.get('verb', '3')).strip() or '3'
    lines.append(f'verb {verb}')

    for extra in cfg.get('extra_lines', []):
        if _is_safe_extra_line(extra):
            lines.append(_clean_ovpn_val(extra))

    conf_file = os.path.join(OPENVPN_CONFIG_PATH, f'{profile_id}.conf')
    _write_secure_file(conf_file, '\n'.join([_clean_ovpn_val(ln) for ln in lines]), 0o600)

    legacy_ovpn = os.path.join(OPENVPN_CONFIG_PATH, f'{profile_id}.ovpn')
    if os.path.exists(legacy_ovpn):
        try:
            os.remove(legacy_ovpn)
        except OSError:
            pass

    if original_id and original_id != profile_id:
        delete_openvpn_config(original_id)
    cfg['original_profile_id'] = profile_id

    return profile_id


def delete_openvpn_config(profile_id):
    """Stop the OpenVPN profile if running and remove its configuration and certs.

    Args:
        profile_id (str): profile identifier without extension.
    """
    disable_openvpn(profile_id)
    for ext in ('.conf', '.ovpn'):
        conf_path = os.path.join(OPENVPN_CONFIG_PATH, f'{profile_id}{ext}')
        if os.path.exists(conf_path):
            try:
                os.remove(conf_path)
            except OSError:
                pass
    cert_dir = os.path.join(OPENVPN_CERTS_PATH, profile_id)
    if os.path.isdir(cert_dir):
        shutil.rmtree(cert_dir, ignore_errors=True)


def openvpn_service_state():
    """Report whether rc.conf has openvpn_enable set to YES."""
    try:
        result = run(['sysrc', '-n', 'openvpn_enable'],
                     stdout=PIPE, stderr=PIPE, check=False, text=True)
    except OSError:
        return 'NO'
    if result.returncode != 0:
        return 'NO'
    return result.stdout.strip() or 'NO'


def _pid_is_alive(pid, expected_comm='openvpn'):
    """Check whether a process ID exists and matches `expected_comm`."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    try:
        res = run(
            ['ps', '-p', str(pid), '-o', 'comm='],
            stdout=PIPE,
            stderr=DEVNULL,
            text=True,
            check=False,
        )
        comm = (res.stdout or '').strip().lower()
        if comm:
            return expected_comm.lower() in comm
    except OSError:
        pass
    return True


def _profile_pid(profile_id):
    """Return the running OpenVPN PID for profile_id, or None."""
    pid_candidates = [f'{OPENVPN_PID_DIR}/openvpn_{profile_id}.pid']
    if profile_id == 'openvpn':
        pid_candidates.append(f'{OPENVPN_PID_DIR}/openvpn.pid')

    for pid_file in pid_candidates:
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r', encoding='utf-8') as handle:
                    pid = int(handle.read().strip())
                if _pid_is_alive(pid):
                    return pid
            except (ValueError, OSError):
                pass

    # Fallback: check pgrep for an openvpn process using this config
    if re.fullmatch(r'[A-Za-z0-9_-]+', profile_id):
        pattern = rf'openvpn.*( |/){profile_id}\.(conf|ovpn)( |$)'
        result = run(
            ['pgrep', '-f', pattern],
            stdout=PIPE, stderr=DEVNULL, check=False, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                return int(result.stdout.strip().splitlines()[0])
            except ValueError:
                pass
    return None


def _clean_openvpn_log_line(line):
    """Strip timestamp and bracketed prefixes from an OpenVPN log line."""
    return re.sub(
        r'^(?:\w{3}\s+\w{3}\s+\d+\s+\d+:\d+:\d+\s+\d{4}|\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})(?:\s+\[[^\]]+\])?\s*',
        '',
        line.strip(),
    ).strip()


def _extract_openvpn_error_from_text(content):
    """Detect known fatal/restart errors in OpenVPN log text."""
    if not content:
        return ''
    if 'AUTH_FAILED' in content or 'auth-failure' in content:
        return 'Authentication failed: invalid username, password, or certificates.'
    if 'TLS Error: TLS handshake failed' in content or 'TLS key negotiation failed' in content:
        return 'TLS handshake failed: VPN server unreachable or certificates invalid.'
    if 'Cannot allocate TUN/TAP' in content or 'Cannot open TUN/TAP' in content:
        return 'Failed to allocate TUN/TAP device. Verify system permissions or tun module.'
    if 'VERIFY ERROR' in content:
        return 'TLS certificate verification failed.'
    match = re.search(r'RESOLVE:\s*Cannot resolve host address:\s*(\S+)', content)
    if match:
        return f'Could not resolve VPN server address: {match.group(1)}'
    match = re.search(r'(Options error:[^\n]+)', content)
    if match:
        return _clean_openvpn_log_line(match.group(1))
    return ''


def _extract_openvpn_log_error(log_file):
    """Read the most descriptive error message from OpenVPN\'s log file."""
    if not os.path.isfile(log_file):
        return ''
    try:
        with open(log_file, 'r', encoding='utf-8', errors='replace') as handle:
            lines = handle.readlines()
    except OSError:
        return ''

    content = ''.join(lines)
    known = _extract_openvpn_error_from_text(content)
    if known:
        return known

    # Look backwards for lines reporting errors
    for raw in reversed(lines):
        cleaned = _clean_openvpn_log_line(raw)
        if not cleaned:
            continue
        lower = cleaned.lower()
        if any(tok in lower for tok in ('error', 'fatal', 'failed', 'cannot', 'sigterm', 'exit')):
            if not lower.startswith('note:') and 'suppress' not in lower:
                return cleaned

    # Fallback to last non-empty line
    for raw in reversed(lines):
        cleaned = _clean_openvpn_log_line(raw)
        if cleaned:
            return cleaned
    return ''


def _tun_device_has_address(dev_name):
    """Check if the given TUN/TAP interface exists and has an IPv4/IPv6 address assigned."""
    if not dev_name or not re.match(r'^[a-zA-Z0-9_.-]+$', dev_name):
        return False
    try:
        res = run(['ifconfig', dev_name], stdout=PIPE, stderr=DEVNULL, text=True, check=False)
        if res.returncode == 0 and ('inet ' in res.stdout or 'inet6 ' in res.stdout):
            return True
    except OSError:
        pass
    try:
        res = run(['ip', '-o', 'addr', 'show', 'dev', dev_name], stdout=PIPE, stderr=DEVNULL, text=True, check=False)
        if res.returncode == 0 and ('inet ' in res.stdout or 'inet6 ' in res.stdout):
            return True
    except OSError:
        pass
    return False


def openvpn_status(profile_id):
    """Return 'Connected', 'Connecting', or 'Disconnected' for an OpenVPN profile."""
    pid = _profile_pid(profile_id)
    if pid is None:
        return 'Disconnected'

    log_file = f'{OPENVPN_PID_DIR}/openvpn_{profile_id}.log'
    if not os.path.isfile(log_file):
        return 'Connected'

    try:
        with open(log_file, 'r', encoding='utf-8', errors='replace') as handle:
            content = handle.read()
    except OSError:
        return 'Connected'

    if 'Initialization Sequence Completed' not in content:
        return 'Connecting'

    last_init_idx = content.rfind('Initialization Sequence Completed')
    after_init = content[last_init_idx:]
    error_markers = (
        'AUTH_FAILED',
        'auth-failure',
        'SIGTERM',
        'SIGUSR1',
        'process restarting',
        'process exiting',
        'Connection reset',
        'Connection refused',
        'Fatal error',
        'ERROR:',
    )
    if any(marker in after_init for marker in error_markers):
        return 'Connecting'

    return 'Connected'


def openvpn_dictionary(service_state=None):
    """Collect all OpenVPN profiles under /usr/local/etc/openvpn and their state.

    Args:
        service_state (str or None): optional cached result of openvpn_service_state().

    Returns:
        dict: 'service', 'default', and 'configs' mapping each profile_id to
            its 'state', 'info' (display name), 'path', 'gateway', 'needs_auth',
            and 'username'.
    """
    if service_state is None:
        service_state = openvpn_service_state()

    main_dict = {
        'service': service_state,
        'default': '',
        'configs': {},
    }

    if not os.path.exists(OPENVPN_CONFIG_PATH):
        return main_dict

    for entry in sorted(os.listdir(OPENVPN_CONFIG_PATH)):
        if not entry.endswith(('.conf', '.ovpn')):
            continue
        full_path = os.path.join(OPENVPN_CONFIG_PATH, entry)
        if not os.path.isfile(full_path):
            continue

        profile_id = os.path.splitext(entry)[0]
        state = openvpn_status(profile_id)
        display_name = profile_id
        gateway = ''
        needs_auth = False
        username = ''
        has_saved_password = False

        try:
            with open(full_path, 'r', encoding='utf-8', errors='replace') as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if line.startswith('# Name ='):
                        display_name = line.split('=', 1)[1].strip() or profile_id
                    elif line.startswith('remote ') and not gateway:
                        parts = line.split()
                        if len(parts) >= 2:
                            gateway = parts[1]
                    elif line.startswith('auth-user-pass'):
                        parts = line.split(None, 1)
                        if len(parts) == 2:
                            auth_path = _resolve_relative_path(OPENVPN_CONFIG_PATH, parts[1])
                            user, pwd = _read_credentials_file(auth_path)
                            username = user
                            has_saved_password = bool(pwd)
                            needs_auth = not (user and pwd)
                        else:
                            needs_auth = True
        except OSError:
            pass

        main_dict['configs'][profile_id] = {
            'state': state,
            'info': display_name,
            'path': full_path,
            'gateway': gateway,
            'needs_auth': needs_auth,
            'username': username,
            'has_saved_password': has_saved_password,
        }

    return main_dict


def _ensure_tun_module():
    """Ensure the FreeBSD if_tun kernel module is loaded."""
    if system() in ('FreeBSD', 'MidnightBSD', 'DragonFly'):
        chk = run(['kldstat', '-q', '-m', 'if_tun'], check=False)
        if chk.returncode != 0:
            run(['kldload', 'if_tun'], stderr=DEVNULL, check=False)


def enable_openvpn(profile_id, username=None, password=None, key_password=None, timeout=12):
    """Bring the specified OpenVPN tunnel up and confirm successful connection.

    Args:
        profile_id (str): the profile identifier without extension.
        username (str or None): optional username if prompted at connect time.
        password (str or None): optional password if prompted at connect time.
        key_password (str or None): optional private key passphrase.
        timeout (int or float): maximum seconds to wait for connection.

    Returns:
        tuple[bool, str]: (success, error_message).
    """
    openvpn_bin = _openvpn_binary()
    if openvpn_bin is None:
        return False, OPENVPN_NOT_INSTALLED_MSG

    conf_path = None
    for ext in ('.conf', '.ovpn'):
        candidate = os.path.join(OPENVPN_CONFIG_PATH, f'{profile_id}{ext}')
        if os.path.isfile(candidate):
            conf_path = candidate
            break

    if not conf_path:
        return False, f'Configuration for "{profile_id}" was not found.'

    if _profile_pid(profile_id) is not None:
        return True, ''

    _ensure_tun_module()

    pid_file = f'{OPENVPN_PID_DIR}/openvpn_{profile_id}.pid'
    status_file = f'{OPENVPN_PID_DIR}/openvpn_{profile_id}.status'
    log_file = f'{OPENVPN_PID_DIR}/openvpn_{profile_id}.log'

    # Remove stale runtime files from prior sessions
    for stale_path in (pid_file, status_file, log_file):
        if os.path.exists(stale_path):
            try:
                os.remove(stale_path)
            except OSError:
                pass

    cmd = [
        openvpn_bin,
        '--daemon', f'openvpn_{profile_id}',
        '--writepid', pid_file,
        '--status', status_file, '5',
        '--log', log_file,
        '--cd', OPENVPN_CONFIG_PATH,
        '--config', conf_path,
    ]

    tmp_dir = (
        OPENVPN_PID_DIR
        if os.path.isdir(OPENVPN_PID_DIR) and os.access(OPENVPN_PID_DIR, os.W_OK)
        else None
    )
    temp_files = []
    try:
        if username is not None and password is not None:
            fd, tmp_auth = tempfile.mkstemp(
                prefix=f'openvpn_{profile_id}_auth_',
                dir=tmp_dir,
            )
            os.close(fd)
            temp_files.append(tmp_auth)
            _write_secure_file(tmp_auth, f'{username}\n{password}', 0o600)
            cmd.extend(['--auth-user-pass', tmp_auth])

        if key_password is not None:
            fd, tmp_askpass = tempfile.mkstemp(
                prefix=f'openvpn_{profile_id}_askpass_',
                dir=tmp_dir,
            )
            os.close(fd)
            temp_files.append(tmp_askpass)
            _write_secure_file(tmp_askpass, key_password, 0o600)
            cmd.extend(['--askpass', tmp_askpass])

        try:
            result = run(cmd, stdout=PIPE, stderr=PIPE, check=False, text=True)
        except FileNotFoundError:
            return False, OPENVPN_NOT_INSTALLED_MSG
        except OSError as exc:
            return False, f'Failed to execute OpenVPN: {exc}'
        if result.returncode != 0:
            err = (result.stderr or result.stdout or '').strip()
            if not err and os.path.isfile(log_file):
                err = _extract_openvpn_log_error(log_file)
            return False, err or 'OpenVPN failed to start.'

        # Poll the daemon log to verify the tunnel actually finishes initialization
        step = 0.3
        max_attempts = max(1, int(timeout / step))
        connected = False
        last_error = ''

        for _ in range(max_attempts):
            sleep(step)
            pid = _profile_pid(profile_id)
            if pid is None:
                last_error = (
                    _extract_openvpn_log_error(log_file)
                    or 'OpenVPN process exited unexpectedly.'
                )
                break

            log_content = ''
            if os.path.isfile(log_file):
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='replace') as handle:
                        log_content = handle.read()
                except OSError:
                    pass

            if log_content:
                detected_err = _extract_openvpn_error_from_text(log_content)
                if detected_err:
                    last_error = detected_err
                    disable_openvpn(profile_id)
                    break

                if 'Initialization Sequence Completed' in log_content:
                    connected = True
                    break

        if not connected:
            if _profile_pid(profile_id) is not None:
                disable_openvpn(profile_id)
            if not last_error:
                last_error = (
                    _extract_openvpn_log_error(log_file)
                    or 'Connection timed out waiting for OpenVPN tunnel to initialize.'
                )
            return False, last_error

        return True, ''
    finally:
        for tmp_path in temp_files:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass


def disable_openvpn(profile_id):
    """Take the specified OpenVPN tunnel down.

    Args:
        profile_id (str): the profile identifier without extension.
    """
    pid = _profile_pid(profile_id)
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            run(['kill', '-TERM', str(pid)], stderr=DEVNULL, check=False)

        for _ in range(15):
            if not _pid_is_alive(pid):
                break
            sleep(0.1)

    for suffix in ('.pid', '.status'):
        path = f'{OPENVPN_PID_DIR}/openvpn_{profile_id}{suffix}'
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
