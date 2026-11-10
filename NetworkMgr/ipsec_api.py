#!/usr/bin/env python

"""IPsec (IKEv2 / IKEv1) and L2TP/IPsec (Windows Server) backend for NetworkMgr.

Provides configuration parsing, importing (.conf, .ipsec, .sswan), exporting,
and runtime connection management on FreeBSD/GhostBSD using StrongSwan
(`security/strongswan`) for IPsec/IKEv2/IKEv1 and `mpd5` (`net/mpd5`) for
L2TP over IPsec (Windows Server, MikroTik, Ubiquiti, FortiGate, etc.).
"""

from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
import glob
import json
import os
import re
import shutil
import tempfile
from subprocess import DEVNULL, PIPE, Popen, TimeoutExpired, run
from time import sleep

IPSEC_DIR = '/usr/local/etc/networkmgr/ipsec'
STRONGSWAN_CONF_DIR = '/usr/local/etc/ipsec.d'
STRONGSWAN_MAIN_CONF = '/usr/local/etc/ipsec.conf'
STRONGSWAN_MAIN_SECRETS = '/usr/local/etc/ipsec.secrets'
RUN_DIR = '/var/run/networkmgr-ipsec'

IPSEC_PROTOCOLS = (
    ('l2tp-ipsec', 'L2TP / IPsec (Windows Server / Corporate L2TP)'),
    ('ikev2-eap', 'IKEv2 with EAP (Username & Password / Windows Server IKEv2)'),
    ('ikev2-psk', 'IKEv2 with Pre-Shared Key (PSK)'),
    ('ikev2-cert', 'IKEv2 with X.509 Certificates'),
    ('ikev1-xauth', 'IKEv1 with XAuth + PSK (Cisco IPsec)'),
)

DEFAULT_IKE_PROPOSALS = (
    'aes256-sha256-modp2048,aes128-sha256-modp2048,'
    'aes256-sha1-modp1024,aes128-sha1-modp1024,3des-sha1-modp1024'
)
DEFAULT_ESP_PROPOSALS = (
    'aes256-sha256,aes128-sha256,aes256-sha1,aes128-sha1,3des-sha1'
)

PROFILE_ID_SAFE_RE = re.compile(r'[^A-Za-z0-9_-]+')
SAFE_HOST_RE = re.compile(r'^[A-Za-z0-9_.:%-]+$')
SAFE_PROPOSAL_RE = re.compile(r'^[A-Za-z0-9_,-]+$')


def _clean_line(value):
    """Strip newlines and NUL bytes to prevent config directive injection."""
    return re.sub(r'[\r\n\x00]+', '', str(value or '')).strip()


def _escape_quoted(value):
    """Escape backslashes and double quotes for StrongSwan and mpd5 quoted strings."""
    cleaned = re.sub(r'[\r\n\x00]+', '', str(value or ''))
    return cleaned.replace('\\', '\\\\').replace('"', '\\"')


def _write_secure_ipsec_file(path, content, mode=0o600):
    """Atomically write an IPsec/mpd5 file with strict permissions and no symlink following."""
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    if os.path.islink(path):
        raise ValueError(f'Refusing to write to symlink: {path}')
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, mode)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(content)
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _pid_is_mpd5(pid):
    """Return True if `pid` is alive and is an `mpd5` process."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        res = run(
            ['ps', '-p', str(pid), '-o', 'comm='],
            stdout=PIPE,
            stderr=DEVNULL,
            universal_newlines=True,
            check=False,
        )
        comm = (res.stdout or '').strip().lower()
        if comm:
            return 'mpd' in comm
    except OSError:
        pass
    return True


def _strongswan_binary():
    """Locate the StrongSwan `ipsec` control binary on FreeBSD/GhostBSD."""
    for candidate in ('/usr/local/sbin/ipsec', '/usr/sbin/ipsec'):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which('ipsec')


def _mpd5_binary():
    """Locate the FreeBSD `mpd5` Netgraph PPP/L2TP daemon binary."""
    for candidate in ('/usr/local/sbin/mpd5', '/usr/sbin/mpd5'):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which('mpd5')


def is_ipsec_installed(protocol='ikev2-eap'):
    """Return True if the required packages for the given IPsec protocol are installed."""
    if _strongswan_binary() is None:
        return False
    if protocol == 'l2tp-ipsec' and _mpd5_binary() is None:
        return False
    return True


def ipsec_missing_packages_message(protocol='ikev2-eap'):
    """Return a clear English alert message describing the missing BSD packages."""
    has_ss = _strongswan_binary() is not None
    has_mpd = _mpd5_binary() is not None
    if protocol == 'l2tp-ipsec':
        if not has_ss and not has_mpd:
            return (
                "L2TP / IPsec VPN requires StrongSwan and mpd5, which are not "
                "installed on this system.\n\n"
                "Please install them by running:\n"
                "  sudo pkg install strongswan mpd5"
            )
        if not has_mpd:
            return (
                "L2TP / IPsec VPN requires mpd5 (Multi-link PPP daemon), which "
                "is not installed on this system.\n\n"
                "Please install it by running:\n"
                "  sudo pkg install mpd5"
            )
    return (
        "IPsec VPN requires StrongSwan, which is not installed on this system.\n\n"
        "Please install it by running:\n"
        "  sudo pkg install strongswan"
    )


def sanitize_ipsec_id(name):
    """Turn a user-visible connection name into a safe filename/identifier."""
    cleaned = PROFILE_ID_SAFE_RE.sub('_', (name or '').strip()).strip('_-')
    return cleaned or 'ipsec_vpn'


def default_ipsec_config(name=''):
    """Return a fresh IPsec / L2TP configuration dictionary with sensible defaults."""
    profile_id = sanitize_ipsec_id(name) if name else ''
    return {
        'vpn_type': 'ipsec',
        'name': name or '',
        'profile_id': profile_id,
        'original_profile_id': profile_id,
        'protocol': 'l2tp-ipsec',
        # Gateway & Identification
        'gateway': '',
        'local_id': '',
        'remote_id': '',
        # Authentication
        'psk': '',
        'username': '',
        'password': '',
        'domain': '',
        'ca_cert': '',
        'user_cert': '',
        'private_key': '',
        'private_key_password': '',
        # Phase 1 / Phase 2 Proposals
        'ike_proposals': DEFAULT_IKE_PROPOSALS,
        'esp_proposals': DEFAULT_ESP_PROPOSALS,
        'aggressive': False,
        # L2TP / PPP Options (Windows Server / mpd5)
        'l2tp_port': '1701',
        'ppp_mschapv2': True,
        'ppp_chap': True,
        'ppp_pap': False,
        'mppe_required': False,
        'mtu': '1400',
        'default_route': True,
        # IPv4 / IPv6 & Static Routes
        'ipv4_method': 'Automatic',
        'ipv4_address': '',
        'ipv4_netmask': '',
        'ipv4_gateway': '',
        'ipv4_dns': '',
        'ipv4_routes': [],
        'ipv6_method': 'Automatic',
        'ipv6_address': '',
        'ipv6_prefixlen': '',
        'ipv6_gateway': '',
        'ipv6_dns': '',
        'ipv6_routes': [],
    }


def detect_ipsec_file(filepath):
    """Return True if `filepath` looks like an IPsec / StrongSwan / L2TP config."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in ('.sswan', '.ipsec'):
        return True
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as fh:
            head = fh.read(8192)
    except OSError:
        return False
    if '# networkmgr-ipsec' in head:
        return True
    if re.search(r'(?m)^\s*conn\s+\S+', head) and re.search(
        r'(?m)^\s*(?:keyexchange|leftauth|rightauth|right|ike|esp)\s*=', head
    ):
        return True
    if head.lstrip().startswith('{') and '"remote"' in head and '"addr"' in head:
        return True
    return False


def parse_ipsec_config(filepath):
    """Parse a NetworkMgr IPsec/L2TP file, StrongSwan `.sswan`, or `ipsec.conf`.

    Args:
        filepath (str): path to `.conf`, `.ipsec`, or `.sswan` file.

    Returns:
        dict: normalized IPsec/L2TP configuration dictionary.
    """
    if not os.path.isfile(filepath):
        raise ValueError(f'Configuration file not found: {filepath}')

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as fh:
            raw_text = fh.read()
    except OSError as exc:
        raise ValueError(f'Could not read {filepath}: {exc}') from exc

    base = os.path.splitext(os.path.basename(filepath))[0]
    cfg = default_ipsec_config(base)
    cfg['profile_id'] = sanitize_ipsec_id(base)
    cfg['original_profile_id'] = cfg['profile_id']

    # Case 1: StrongSwan Android/desktop .sswan JSON profile
    stripped = raw_text.lstrip()
    if stripped.startswith('{'):
        try:
            data = json.loads(raw_text)
            cfg['name'] = data.get('name', base)
            cfg['profile_id'] = sanitize_ipsec_id(cfg['name'])
            remote = data.get('remote', {})
            cfg['gateway'] = remote.get('addr', '')
            cfg['remote_id'] = remote.get('id', '')
            local = data.get('local', {})
            auth = local.get('auth', 'eap')
            if auth == 'psk':
                cfg['protocol'] = 'ikev2-psk'
                cfg['psk'] = local.get('psk', '')
            elif auth in ('pubkey', 'cert'):
                cfg['protocol'] = 'ikev2-cert'
            else:
                cfg['protocol'] = 'ikev2-eap'
                cfg['username'] = local.get('eap_id', '') or local.get('id', '')
            return cfg
        except (ValueError, TypeError):
            pass

    # Case 2: Standard StrongSwan ipsec.conf (without networkmgr-ipsec header)
    if '# networkmgr-ipsec' not in raw_text and re.search(
        r'(?m)^\s*conn\s+\S+', raw_text
    ):
        conn_match = re.search(r'(?m)^\s*conn\s+([^\s#]+)', raw_text)
        if conn_match and conn_match.group(1) != '%default':
            cfg['name'] = conn_match.group(1)
        keyex = 'ikev2'
        leftauth = ''
        conn_type = 'tunnel'
        for line in raw_text.splitlines():
            sline = line.strip()
            if not sline or sline.startswith('#'):
                continue
            if '=' not in sline:
                continue
            k, v = [p.strip().strip('"') for p in sline.split('=', 1)]
            kl = k.lower()
            if kl == 'right':
                cfg['gateway'] = v
            elif kl == 'rightid':
                cfg['remote_id'] = v
            elif kl in ('leftid', 'eap_identity'):
                cfg['local_id'] = v
                if not cfg['username']:
                    cfg['username'] = v
            elif kl == 'keyexchange':
                keyex = v.lower()
            elif kl in ('leftauth', 'authby'):
                leftauth = v.lower()
            elif kl == 'type':
                conn_type = v.lower()
            elif kl == 'ike':
                cfg['ike_proposals'] = v.rstrip('!')
            elif kl == 'esp':
                cfg['esp_proposals'] = v.rstrip('!')
        if conn_type == 'transport':
            cfg['protocol'] = 'l2tp-ipsec'
        elif 'ikev1' in keyex:
            cfg['protocol'] = 'ikev1-xauth'
        elif 'psk' in leftauth or 'secret' in leftauth:
            cfg['protocol'] = 'ikev2-psk'
        elif 'pubkey' in leftauth or 'cert' in leftauth:
            cfg['protocol'] = 'ikev2-cert'
        else:
            cfg['protocol'] = 'ikev2-eap'
        return cfg

    # Case 3: NetworkMgr IPsec/L2TP profile format
    bool_keys = {
        'aggressive',
        'ppp_mschapv2',
        'ppp_chap',
        'ppp_pap',
        'mppe_required',
        'default_route',
    }
    for line in raw_text.splitlines():
        sline = line.strip()
        if not sline or sline.startswith('#'):
            continue
        if '=' not in sline:
            continue
        key, val = [part.strip() for part in sline.split('=', 1)]
        if key in ('ipv4_route', 'ipv6_route'):
            parts = [p.strip() for p in val.split(',')]
            if key == 'ipv4_route' and len(parts) >= 2:
                cfg['ipv4_routes'].append({
                    'address': parts[0],
                    'netmask': parts[1],
                    'gateway': parts[2] if len(parts) > 2 else '',
                    'metric': parts[3] if len(parts) > 3 else '',
                })
            elif key == 'ipv6_route' and len(parts) >= 2:
                cfg['ipv6_routes'].append({
                    'address': parts[0],
                    'prefixlen': parts[1],
                    'gateway': parts[2] if len(parts) > 2 else '',
                    'metric': parts[3] if len(parts) > 3 else '',
                })
            continue
        if key in bool_keys:
            cfg[key] = val.lower() in ('1', 'true', 'yes', 'on')
        elif key in cfg:
            cfg[key] = val

    return cfg


def save_ipsec_config(cfg, target_dir=IPSEC_DIR):
    """Save an IPsec / L2TP configuration dictionary to disk.

    Args:
        cfg (dict): IPsec/L2TP configuration dictionary.
        target_dir (str): target directory (`/usr/local/etc/networkmgr/ipsec`).

    Returns:
        str: path to the saved `.conf` file.
    """
    display_name = _clean_line(cfg.get('name') or cfg.get('profile_id') or '')
    profile_id = sanitize_ipsec_id(display_name)
    old_profile_id = _clean_line(cfg.get('original_profile_id') or '')
    cfg['profile_id'] = profile_id
    if not cfg.get('name'):
        cfg['name'] = profile_id

    gateway = _clean_line(cfg.get('gateway') or '')
    if not gateway:
        raise ValueError('Gateway (Server Address) is required.')
    if not SAFE_HOST_RE.fullmatch(gateway):
        raise ValueError(f'Invalid Gateway address: "{gateway}"')

    port_val = _clean_line(cfg.get('l2tp_port') or '1701') or '1701'
    if not port_val.isdigit() or not (1 <= int(port_val) <= 65535):
        raise ValueError('L2TP UDP Port must be an integer between 1 and 65535.')

    mtu_val = _clean_line(cfg.get('mtu') or '1400') or '1400'
    if not mtu_val.isdigit() or not (576 <= int(mtu_val) <= 65535):
        raise ValueError('PPP MTU must be an integer between 576 and 65535.')

    ike_val = _clean_line(cfg.get('ike_proposals') or DEFAULT_IKE_PROPOSALS) or DEFAULT_IKE_PROPOSALS
    if not SAFE_PROPOSAL_RE.fullmatch(ike_val):
        raise ValueError('Phase 1 (IKE) proposals contain invalid characters.')

    esp_val = _clean_line(cfg.get('esp_proposals') or DEFAULT_ESP_PROPOSALS) or DEFAULT_ESP_PROPOSALS
    if not SAFE_PROPOSAL_RE.fullmatch(esp_val):
        raise ValueError('Phase 2 (ESP) proposals contain invalid characters.')

    os.makedirs(target_dir, exist_ok=True)
    try:
        os.chmod(target_dir, 0o700)
    except OSError:
        pass
    if old_profile_id and old_profile_id != profile_id:
        old_path = os.path.join(target_dir, f'{ sanitize_ipsec_id(old_profile_id) }.conf')
        if os.path.isfile(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
    cfg['original_profile_id'] = profile_id

    lines = [
        '# networkmgr-ipsec configuration',
        f'name = {_clean_line(cfg.get("name", profile_id))}',
        f'protocol = {_clean_line(cfg.get("protocol", "l2tp-ipsec"))}',
        f'gateway = {gateway}',
        f'local_id = {_clean_line(cfg.get("local_id", ""))}',
        f'remote_id = {_clean_line(cfg.get("remote_id", ""))}',
        f'psk = {_clean_line(cfg.get("psk", ""))}',
        f'username = {_clean_line(cfg.get("username", ""))}',
        f'password = {_clean_line(cfg.get("password", ""))}',
        f'domain = {_clean_line(cfg.get("domain", ""))}',
        f'ca_cert = {_clean_line(cfg.get("ca_cert", ""))}',
        f'user_cert = {_clean_line(cfg.get("user_cert", ""))}',
        f'private_key = {_clean_line(cfg.get("private_key", ""))}',
        f'private_key_password = {_clean_line(cfg.get("private_key_password", ""))}',
        f'ike_proposals = {ike_val}',
        f'esp_proposals = {esp_val}',
        f'aggressive = {bool(cfg.get("aggressive", False))}',
        f'l2tp_port = {port_val}',
        f'ppp_mschapv2 = {bool(cfg.get("ppp_mschapv2", True))}',
        f'ppp_chap = {bool(cfg.get("ppp_chap", True))}',
        f'ppp_pap = {bool(cfg.get("ppp_pap", False))}',
        f'mppe_required = {bool(cfg.get("mppe_required", False))}',
        f'mtu = {mtu_val}',
        f'default_route = {bool(cfg.get("default_route", True))}',
        f'ipv4_method = {_clean_line(cfg.get("ipv4_method", "Automatic"))}',
        f'ipv4_address = {_clean_line(cfg.get("ipv4_address", ""))}',
        f'ipv4_netmask = {_clean_line(cfg.get("ipv4_netmask", ""))}',
        f'ipv4_gateway = {_clean_line(cfg.get("ipv4_gateway", ""))}',
        f'ipv4_dns = {_clean_line(cfg.get("ipv4_dns", ""))}',
        f'ipv6_method = {_clean_line(cfg.get("ipv6_method", "Automatic"))}',
        f'ipv6_address = {_clean_line(cfg.get("ipv6_address", ""))}',
        f'ipv6_prefixlen = {_clean_line(cfg.get("ipv6_prefixlen", ""))}',
        f'ipv6_gateway = {_clean_line(cfg.get("ipv6_gateway", ""))}',
        f'ipv6_dns = {_clean_line(cfg.get("ipv6_dns", ""))}',
    ]

    for rt in cfg.get('ipv4_routes') or []:
        addr = _clean_line(rt.get('address') or '')
        mask = _clean_line(rt.get('netmask') or '')
        gw = _clean_line(rt.get('gateway') or '')
        metric = _clean_line(rt.get('metric') or '')
        if addr and mask:
            try:
                IPv4Address(addr)
                if mask.isdigit():
                    if not (0 <= int(mask) <= 32):
                        raise ValueError()
                else:
                    IPv4Address(mask)
                if gw:
                    IPv4Address(gw)
            except ValueError as exc:
                raise ValueError(f'Invalid IPv4 static route "{addr} / {mask}": {exc}') from exc
            lines.append(f'ipv4_route = {addr},{mask},{gw},{metric}')

    for rt6 in cfg.get('ipv6_routes') or []:
        addr6 = _clean_line(rt6.get('address') or '')
        plen = _clean_line(rt6.get('prefixlen') or '64').lstrip('/')
        gw6 = _clean_line(rt6.get('gateway') or '')
        metric6 = _clean_line(rt6.get('metric') or '')
        if addr6:
            try:
                IPv6Address(addr6.split('/')[0])
                if not plen.isdigit() or not (0 <= int(plen) <= 128):
                    raise ValueError('Invalid prefix length')
                if gw6:
                    IPv6Address(gw6.split('%')[0])
            except ValueError as exc:
                raise ValueError(f'Invalid IPv6 static route "{addr6}/{plen}": {exc}') from exc
            lines.append(f'ipv6_route = {addr6},{plen},{gw6},{metric6}')

    lines.append('')
    conf_path = os.path.join(target_dir, f'{profile_id}.conf')
    _write_secure_ipsec_file(conf_path, '\n'.join(lines), 0o600)
    return conf_path


def delete_ipsec_config(profile_id, target_dir=IPSEC_DIR):
    """Stop and remove an IPsec / L2TP configuration profile."""
    profile_id = sanitize_ipsec_id(profile_id)
    disable_ipsec(profile_id)
    conf_path = os.path.join(target_dir, f'{profile_id}.conf')
    if os.path.isfile(conf_path):
        try:
            os.remove(conf_path)
        except OSError:
            pass
    for ext in ('conf', 'secrets'):
        ss_file = os.path.join(STRONGSWAN_CONF_DIR, f'nm-{profile_id}.{ext}')
        if os.path.isfile(ss_file):
            try:
                os.remove(ss_file)
            except OSError:
                pass


def ipsec_configs(target_dir=IPSEC_DIR):
    """Return sorted list of `.conf` files in `/usr/local/etc/networkmgr/ipsec`."""
    if not os.path.isdir(target_dir):
        return []
    return sorted(glob.glob(f'{target_dir}/*.conf'))


def ipsec_is_connected(profile_id):
    """Return True if the given IPsec / L2TP profile is currently active."""
    profile_id = sanitize_ipsec_id(profile_id)
    state_file = os.path.join(RUN_DIR, f'{profile_id}.state')
    if not os.path.isfile(state_file):
        return False
    pid_file = os.path.join(RUN_DIR, f'{profile_id}.pid')
    if os.path.isfile(pid_file):
        try:
            with open(pid_file, 'r', encoding='utf-8') as fh:
                pid = int(fh.read().strip())
            return _pid_is_mpd5(pid)
        except (ValueError, OSError):
            return False
    ipsec_bin = _strongswan_binary()
    if ipsec_bin:
        try:
            res = run(
                [ipsec_bin, 'status', f'nm-{profile_id}'],
                stdout=PIPE,
                stderr=PIPE,
                universal_newlines=True,
                check=False,
            )
            if 'ESTABLISHED' in (res.stdout or '') or 'INSTALLED' in (res.stdout or ''):
                return True
        except OSError:
            pass
    return False


def ipsec_dictionary(target_dir=IPSEC_DIR):
    """Build the dictionary of IPsec/L2TP profiles and their connection states."""
    output = {'configs': {}}
    for conf_path in ipsec_configs(target_dir):
        profile_id = os.path.splitext(os.path.basename(conf_path))[0]
        try:
            parsed = parse_ipsec_config(conf_path)
            display_name = parsed.get('name') or profile_id
            gateway = parsed.get('gateway', '')
            protocol = parsed.get('protocol', 'l2tp-ipsec')
        except ValueError:
            display_name = profile_id
            gateway = ''
            protocol = 'l2tp-ipsec'

        proto_labels = dict(IPSEC_PROTOCOLS)
        output['configs'][profile_id] = {
            'state': 'Connected' if ipsec_is_connected(profile_id) else 'Disconnected',
            'info': display_name,
            'path': conf_path,
            'gateway': gateway,
            'protocol': protocol,
            'protocol_label': proto_labels.get(protocol, 'IPsec'),
        }
    return output


def _ensure_strongswan_includes():
    """Ensure StrongSwan main ipsec.conf and ipsec.secrets include ipsec.d/*."""
    os.makedirs(STRONGSWAN_CONF_DIR, exist_ok=True)
    inc_conf = f'include {STRONGSWAN_CONF_DIR}/*.conf'
    if os.path.isfile(STRONGSWAN_MAIN_CONF):
        try:
            with open(STRONGSWAN_MAIN_CONF, 'r', encoding='utf-8') as fh:
                content = fh.read()
            if inc_conf not in content:
                with open(STRONGSWAN_MAIN_CONF, 'a', encoding='utf-8') as fh:
                    fh.write(f'\n{inc_conf}\n')
        except OSError:
            pass
    else:
        try:
            with open(STRONGSWAN_MAIN_CONF, 'w', encoding='utf-8') as fh:
                fh.write(f'config setup\n\n{inc_conf}\n')
        except OSError:
            pass

    inc_sec = f'include {STRONGSWAN_CONF_DIR}/*.secrets'
    if os.path.isfile(STRONGSWAN_MAIN_SECRETS):
        try:
            with open(STRONGSWAN_MAIN_SECRETS, 'r', encoding='utf-8') as fh:
                content = fh.read()
            if inc_sec not in content:
                with open(STRONGSWAN_MAIN_SECRETS, 'a', encoding='utf-8') as fh:
                    fh.write(f'\n{inc_sec}\n')
        except OSError:
            pass
    else:
        try:
            fd = os.open(
                STRONGSWAN_MAIN_SECRETS,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                fh.write(f'{inc_sec}\n')
        except OSError:
            pass


def _write_strongswan_files(profile_id, cfg):
    """Write StrongSwan connection and secrets snippets for `profile_id`."""
    _ensure_strongswan_includes()
    profile_id = sanitize_ipsec_id(profile_id)
    protocol = _clean_line(cfg.get('protocol', 'l2tp-ipsec'))
    gateway = _clean_line(cfg.get('gateway', ''))
    if not SAFE_HOST_RE.fullmatch(gateway):
        raise ValueError(f'Invalid gateway address: "{gateway}"')
    local_id = _escape_quoted(cfg.get('local_id', '').strip())
    remote_id = _escape_quoted(cfg.get('remote_id', '').strip())
    ike = _clean_line(cfg.get('ike_proposals', DEFAULT_IKE_PROPOSALS)) or DEFAULT_IKE_PROPOSALS
    if not SAFE_PROPOSAL_RE.fullmatch(ike):
        ike = DEFAULT_IKE_PROPOSALS
    esp = _clean_line(cfg.get('esp_proposals', DEFAULT_ESP_PROPOSALS)) or DEFAULT_ESP_PROPOSALS
    if not SAFE_PROPOSAL_RE.fullmatch(esp):
        esp = DEFAULT_ESP_PROPOSALS
    port = _clean_line(cfg.get('l2tp_port', '1701')) or '1701'
    if not port.isdigit() or not (1 <= int(port) <= 65535):
        port = '1701'

    conn_lines = [
        f'conn nm-{profile_id}',
        '    auto=add',
        '    left=%defaultroute',
        f'    right={gateway}',
        f'    ike={ike}',
        f'    esp={esp}',
        '    dpdaction=clear',
        '    dpddelay=30s',
    ]
    if local_id:
        conn_lines.append(f'    leftid="{local_id}"')
    if remote_id:
        conn_lines.append(f'    rightid="{remote_id}"')

    secret_lines = []
    psk = _escape_quoted(cfg.get('psk', ''))
    user = _escape_quoted(cfg.get('username', '').strip())
    pw = _escape_quoted(cfg.get('password', ''))

    if protocol == 'l2tp-ipsec':
        conn_lines.extend([
            '    keyexchange=ikev1',
            '    authby=secret',
            '    type=transport',
            f'    leftprotoport=17/{port}',
            f'    rightprotoport=17/{port}',
            '    rekey=no',
        ])
        secret_lines.append(f'%any {gateway} : PSK "{psk}"')
    elif protocol == 'ikev2-psk':
        conn_lines.extend([
            '    keyexchange=ikev2',
            '    leftauth=psk',
            '    rightauth=psk',
            '    leftsourceip=%config',
            '    rightsubnet=0.0.0.0/0',
        ])
        secret_lines.append(f'%any {gateway} : PSK "{psk}"')
    elif protocol == 'ikev2-cert':
        conn_lines.extend([
            '    keyexchange=ikev2',
            '    leftauth=pubkey',
            '    rightauth=pubkey',
            '    leftsourceip=%config',
            '    rightsubnet=0.0.0.0/0',
        ])
        ucert = _escape_quoted(cfg.get('user_cert', '').strip())
        cacert = _escape_quoted(cfg.get('ca_cert', '').strip())
        pkey = _escape_quoted(cfg.get('private_key', '').strip())
        if ucert:
            conn_lines.append(f'    leftcert="{ucert}"')
        if cacert:
            conn_lines.append(f'    rightca="{cacert}"')
        if pkey:
            key_pw = _escape_quoted(cfg.get('private_key_password', ''))
            if key_pw:
                secret_lines.append(f' : RSA "{pkey}" "{key_pw}"')
            else:
                secret_lines.append(f' : RSA "{pkey}"')
    elif protocol == 'ikev1-xauth':
        conn_lines.extend([
            '    keyexchange=ikev1',
            '    leftauth=psk',
            '    rightauth=psk',
            '    leftauth2=xauth',
            '    leftsourceip=%config',
            '    rightsubnet=0.0.0.0/0',
        ])
        if cfg.get('aggressive'):
            conn_lines.append('    aggressive=yes')
        if user:
            conn_lines.append(f'    xauth_identity="{user}"')
        secret_lines.append(f'%any {gateway} : PSK "{psk}"')
        if user:
            secret_lines.append(f'"{user}" : XAUTH "{pw}"')
    else:  # ikev2-eap (Windows Server IKEv2 / EAP-MSCHAPv2)
        conn_lines.extend([
            '    keyexchange=ikev2',
            '    leftauth=eap-mschapv2',
            '    rightauth=pubkey',
            '    leftsourceip=%config',
            '    rightsubnet=0.0.0.0/0',
        ])
        if user:
            conn_lines.append(f'    eap_identity="{user}"')
        cacert = _escape_quoted(cfg.get('ca_cert', '').strip())
        if cacert:
            conn_lines.append(f'    rightca="{cacert}"')
        else:
            conn_lines.append('    rightsendcert=never')
        if user:
            secret_lines.append(f'"{user}" : EAP "{pw}"')

    conn_path = os.path.join(STRONGSWAN_CONF_DIR, f'nm-{profile_id}.conf')
    _write_secure_ipsec_file(conn_path, '\n'.join(conn_lines) + '\n', 0o600)

    sec_path = os.path.join(STRONGSWAN_CONF_DIR, f'nm-{profile_id}.secrets')
    _write_secure_ipsec_file(sec_path, '\n'.join(secret_lines) + '\n', 0o600)


def _write_mpd5_config(profile_id, cfg):
    """Write the FreeBSD `mpd5` L2TP client configuration for `profile_id`."""
    profile_id = sanitize_ipsec_id(profile_id)
    mpd_dir = os.path.join(RUN_DIR, profile_id)
    os.makedirs(mpd_dir, exist_ok=True)
    try:
        os.chmod(mpd_dir, 0o700)
    except OSError:
        pass

    gateway = _clean_line(cfg.get('gateway', ''))
    if not SAFE_HOST_RE.fullmatch(gateway):
        raise ValueError(f'Invalid gateway address: "{gateway}"')
    port = _clean_line(cfg.get('l2tp_port', '1701')) or '1701'
    if not port.isdigit() or not (1 <= int(port) <= 65535):
        port = '1701'
    user = _clean_line(cfg.get('username', ''))
    domain = _clean_line(cfg.get('domain', ''))
    raw_full_user = f'{domain}\\{user}' if domain and user else user
    full_user = _escape_quoted(raw_full_user)
    password = _escape_quoted(cfg.get('password', ''))
    mtu = _clean_line(cfg.get('mtu', '1400')) or '1400'
    if not mtu.isdigit() or not (576 <= int(mtu) <= 65535):
        mtu = '1400'

    iface_lines = [
        '    set iface disable on-demand',
        '    set iface idle 0',
        f'    set iface mtu {mtu}',
    ]
    if cfg.get('default_route', True):
        iface_lines.append('    set iface route default')
    for rt in cfg.get('ipv4_routes') or []:
        addr = _clean_line(rt.get('address') or '')
        mask = _clean_line(rt.get('netmask') or '')
        if addr and mask:
            try:
                net_obj = IPv4Network(f'{addr}/{mask}', strict=False)
                iface_lines.append(f'    set iface route {net_obj.with_prefixlen}')
            except ValueError:
                pass

    ipcp_range = '0.0.0.0/0 0.0.0.0/0'
    if cfg.get('ipv4_method') == 'Manual' and cfg.get('ipv4_address'):
        try:
            addr4 = str(IPv4Address(_clean_line(cfg['ipv4_address'])))
            ipcp_range = f'{addr4}/32 0.0.0.0/0'
        except ValueError:
            pass

    auth_lines = []
    if cfg.get('ppp_mschapv2', True):
        auth_lines.append('    set link accept mschapv2')
    if cfg.get('ppp_chap', True):
        auth_lines.append('    set link accept chap-md5 chap-msv1 chap-msv2')
    if cfg.get('ppp_pap', False):
        auth_lines.append('    set link accept pap')

    ccp_lines = ['    set bundle enable compression', '    set ccp yes mppc']
    if cfg.get('mppe_required', False):
        ccp_lines.append('    set mppc yes e40 e128 stateless')
    else:
        ccp_lines.append('    set mppc yes e40 e56 e128 stateless')

    mpd_conf = '\n'.join([
        'startup:',
        '',
        'default:',
        '    load l2tp_client',
        '',
        'l2tp_client:',
        '    create bundle static B1',
        *iface_lines,
        '    set ipcp ranges ' + ipcp_range,
        *ccp_lines,
        '    create link static L1 l2tp',
        '    set link action bundle B1',
        f'    set link mtu {mtu}',
        '    set link keep-alive 20 75',
        *auth_lines,
        f'    set auth authname "{full_user}"',
        f'    set auth password "{password}"',
        f'    set l2tp peer {gateway} {port}',
        '    open',
        '',
    ])

    mpd_path = os.path.join(mpd_dir, 'mpd.conf')
    _write_secure_ipsec_file(mpd_path, mpd_conf, 0o600)
    return mpd_dir


def _apply_custom_routes(cfg):
    """Apply validated static IPv4/IPv6 routes configured on the profile."""
    for rt in cfg.get('ipv4_routes') or []:
        addr = _clean_line(rt.get('address') or '')
        mask = _clean_line(rt.get('netmask') or '')
        gw = _clean_line(rt.get('gateway') or cfg.get('ipv4_gateway') or '')
        if addr and mask and gw:
            try:
                addr_ok = str(IPv4Address(addr))
                gw_ok = str(IPv4Address(gw))
                if mask.isdigit() and 0 <= int(mask) <= 32:
                    mask_ok = str(IPv4Network(f'0.0.0.0/{mask}').netmask)
                else:
                    mask_ok = str(IPv4Address(mask))
                run(
                    ['route', '-n', 'add', '-net', addr_ok, gw_ok, mask_ok],
                    stdout=PIPE,
                    stderr=PIPE,
                    check=False,
                )
            except (ValueError, OSError):
                pass
    for rt6 in cfg.get('ipv6_routes') or []:
        addr6 = _clean_line(rt6.get('address') or '')
        plen = _clean_line(rt6.get('prefixlen') or '64').lstrip('/')
        gw6 = _clean_line(rt6.get('gateway') or cfg.get('ipv6_gateway') or '')
        if addr6 and gw6:
            try:
                net6_ok = str(IPv6Network(f'{addr6}/{plen}', strict=False))
                gw6_parts = gw6.split('%', 1)
                gw6_ip = str(IPv6Address(gw6_parts[0]))
                if len(gw6_parts) == 2 and re.fullmatch(r'[A-Za-z0-9_.-]+', gw6_parts[1]):
                    gw6_ok = f'{gw6_ip}%{gw6_parts[1]}'
                else:
                    gw6_ok = gw6_ip
                run(
                    ['route', '-n', 'add', '-inet6', net6_ok, gw6_ok],
                    stdout=PIPE,
                    stderr=PIPE,
                    check=False,
                )
            except (ValueError, OSError):
                pass


def _run_daemon_cmd(args, timeout=15):
    """Run a command that may spawn background daemons without hanging on PIPE EOF."""
    with tempfile.TemporaryFile() as tmp_out:
        proc = Popen(
            args,
            stdin=DEVNULL,
            stdout=tmp_out,
            stderr=tmp_out,
            close_fds=True,
        )
        try:
            proc.wait(timeout=timeout)
        except TimeoutExpired:
            proc.kill()
            return 1, 'Command timed out.'
        tmp_out.seek(0)
        output = tmp_out.read().decode('utf-8', errors='replace').strip()
        return proc.returncode, output


def enable_ipsec(profile_id, target_dir=IPSEC_DIR):
    """Start an IPsec (IKEv2/IKEv1) or L2TP/IPsec connection.

    Returns:
        tuple[bool, str]: `(True, '')` on success, or `(False, error_message)`.
    """
    profile_id = sanitize_ipsec_id(profile_id)
    conf_path = os.path.join(target_dir, f'{profile_id}.conf')
    if not os.path.isfile(conf_path):
        return False, f'Configuration not found: {conf_path}'

    try:
        cfg = parse_ipsec_config(conf_path)
    except ValueError as err:
        return False, str(err)

    protocol = cfg.get('protocol', 'l2tp-ipsec')
    if not is_ipsec_installed(protocol):
        return False, ipsec_missing_packages_message(protocol)

    os.makedirs(RUN_DIR, exist_ok=True)
    _write_strongswan_files(profile_id, cfg)

    ipsec_bin = _strongswan_binary()
    try:
        # Ensure strongSwan charon/starter is running and reload configs
        status_rc, _ = _run_daemon_cmd([ipsec_bin, 'status'], timeout=5)
        if status_rc != 0:
            _run_daemon_cmd([ipsec_bin, 'start'], timeout=10)
            sleep(1.0)
        else:
            _run_daemon_cmd([ipsec_bin, 'reload'], timeout=5)
            _run_daemon_cmd([ipsec_bin, 'rereadsecrets'], timeout=5)
            sleep(0.4)

        up_rc, output_text = _run_daemon_cmd(
            [ipsec_bin, 'up', f'nm-{profile_id}'],
            timeout=20,
        )
        if up_rc != 0 and 'established' not in output_text.lower():
            return False, (output_text.strip() or 'StrongSwan failed to establish IPsec SA.')
    except OSError as exc:
        return False, str(exc)

    if protocol == 'l2tp-ipsec':
        mpd_bin = _mpd5_binary()
        mpd_dir = _write_mpd5_config(profile_id, cfg)
        pid_file = os.path.join(RUN_DIR, f'{profile_id}.pid')
        try:
            mpd_rc, err = _run_daemon_cmd(
                [
                    mpd_bin,
                    '-b',
                    '-d', mpd_dir,
                    '-p', pid_file,
                    '-s', f'networkmgr_{profile_id}',
                    'l2tp_client',
                ],
                timeout=10,
            )
            if mpd_rc not in (0, None):
                return False, (err or 'mpd5 failed to start L2TP session.').strip()
        except Exception as exc:
            return False, str(exc)

    state_file = os.path.join(RUN_DIR, f'{profile_id}.state')
    try:
        with open(state_file, 'w', encoding='utf-8') as fh:
            fh.write('connected\n')
    except OSError:
        pass

    _apply_custom_routes(cfg)
    return True, ''


def disable_ipsec(profile_id):
    """Stop an active IPsec or L2TP/IPsec connection."""
    profile_id = sanitize_ipsec_id(profile_id)
    pid_file = os.path.join(RUN_DIR, f'{profile_id}.pid')
    if os.path.isfile(pid_file):
        try:
            with open(pid_file, 'r', encoding='utf-8') as fh:
                pid_str = fh.read().strip()
            if pid_str.isdigit() and _pid_is_mpd5(int(pid_str)):
                run(['kill', '-TERM', pid_str], stdout=PIPE, stderr=PIPE, check=False)
        except OSError:
            pass
        try:
            os.remove(pid_file)
        except OSError:
            pass

    ipsec_bin = _strongswan_binary()
    if ipsec_bin:
        try:
            run(
                [ipsec_bin, 'down', f'nm-{profile_id}'],
                stdout=PIPE,
                stderr=PIPE,
                check=False,
            )
        except OSError:
            pass

    state_file = os.path.join(RUN_DIR, f'{profile_id}.state')
    if os.path.isfile(state_file):
        try:
            os.remove(state_file)
        except OSError:
            pass
