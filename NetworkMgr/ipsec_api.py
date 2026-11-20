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
import socket
import tempfile
from subprocess import DEVNULL, PIPE, Popen, TimeoutExpired, run
from time import sleep

from NetworkMgr.logger import log_debug, log_info, log_warning, log_error

IPSEC_DIR = '/usr/local/etc/networkmgr/ipsec'
STRONGSWAN_CONF_DIR = '/usr/local/etc/ipsec.d'
STRONGSWAN_MAIN_CONF = '/usr/local/etc/ipsec.conf'
STRONGSWAN_MAIN_SECRETS = '/usr/local/etc/ipsec.secrets'
SWANCTL_DIR = '/usr/local/etc/swanctl'
SWANCTL_CONF_DIR = '/usr/local/etc/swanctl/conf.d'
SWANCTL_MAIN_CONF = '/usr/local/etc/swanctl/swanctl.conf'
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
    """Locate the StrongSwan `ipsec`, `strongswan`, or `swanctl` binary on FreeBSD/GhostBSD."""
    for candidate in (
        '/usr/local/sbin/ipsec',
        '/usr/local/bin/ipsec',
        '/usr/sbin/ipsec',
        '/usr/bin/ipsec',
        '/usr/local/sbin/strongswan',
        '/usr/local/bin/strongswan',
        '/usr/sbin/strongswan',
        '/usr/bin/strongswan',
        '/usr/local/sbin/swanctl',
        '/usr/local/bin/swanctl',
        '/usr/sbin/swanctl',
        '/usr/bin/swanctl',
    ):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    for name in ('ipsec', 'strongswan', 'swanctl'):
        found = shutil.which(name)
        if found:
            return found
    return None


def _mpd5_binary():
    """Locate the FreeBSD `mpd5` Netgraph PPP/L2TP daemon binary."""
    for candidate in (
        '/usr/local/sbin/mpd5',
        '/usr/local/bin/mpd5',
        '/usr/sbin/mpd5',
        '/usr/bin/mpd5',
        '/usr/local/sbin/mpd',
        '/usr/local/bin/mpd',
        '/usr/sbin/mpd',
        '/usr/bin/mpd',
    ):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    for name in ('mpd5', 'mpd'):
        found = shutil.which(name)
        if found:
            return found
    return None


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
        'original_profile_id': None,
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

    base_dir = os.path.dirname(os.path.abspath(filepath))
    base = os.path.splitext(os.path.basename(filepath))[0]
    cfg = default_ipsec_config(base)
    cfg['profile_id'] = sanitize_ipsec_id(base)
    is_internal_profile = False
    if os.path.exists(IPSEC_DIR):
        try:
            if os.path.samefile(base_dir, IPSEC_DIR):
                cfg['original_profile_id'] = cfg['profile_id']
                is_internal_profile = True
        except OSError:
            pass

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
            if not is_internal_profile:
                cfg['profile_id'] = sanitize_ipsec_id(cfg['name'])
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
        elif key in cfg and key not in (
            'vpn_type',
            'profile_id',
            'original_profile_id',
            'ipv4_routes',
            'ipv6_routes',
        ):
            cfg[key] = val

    if not is_internal_profile and cfg.get('name'):
        cfg['profile_id'] = sanitize_ipsec_id(cfg['name'])

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
    raw_old_id = _clean_line(cfg.get('original_profile_id') or '')
    old_profile_id = sanitize_ipsec_id(raw_old_id) if raw_old_id else ''
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

    if old_profile_id and old_profile_id != profile_id:
        delete_ipsec_config(old_profile_id, target_dir=target_dir)
    cfg['original_profile_id'] = profile_id
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
    removed_ss = False
    for ext in ('conf', 'secrets'):
        ss_file = os.path.join(STRONGSWAN_CONF_DIR, f'nm-{profile_id}.{ext}')
        if os.path.isfile(ss_file):
            try:
                os.remove(ss_file)
                removed_ss = True
            except OSError:
                pass
    sc_file = os.path.join(SWANCTL_CONF_DIR, f'nm-{profile_id}.conf')
    if os.path.isfile(sc_file):
        try:
            os.remove(sc_file)
            removed_ss = True
        except OSError:
            pass
    mpd_dir = os.path.join(RUN_DIR, profile_id)
    if os.path.isdir(mpd_dir):
        shutil.rmtree(mpd_dir, ignore_errors=True)
    if removed_ss:
        ipsec_bin = _strongswan_binary()
        if ipsec_bin:
            try:
                if os.path.basename(ipsec_bin) == 'swanctl':
                    _run_daemon_cmd([ipsec_bin, '--load-all'], timeout=5)
                else:
                    status_rc, _ = _run_daemon_cmd([ipsec_bin, 'status'], timeout=5)
                    if status_rc == 0:
                        _run_daemon_cmd([ipsec_bin, 'reload'], timeout=5)
                        _run_daemon_cmd([ipsec_bin, 'rereadsecrets'], timeout=5)
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
            alive = _pid_is_mpd5(pid)
            if not alive:
                if os.path.isfile(state_file):
                    try:
                        os.remove(state_file)
                    except OSError:
                        pass
                return False
            # For mpd5 L2TP, verify that up.info exists (interface is UP and has IP assigned)
            info_file = os.path.join(RUN_DIR, profile_id, 'up.info')
            if not os.path.isfile(info_file):
                return False
            return True
        except (ValueError, OSError):
            return False
    ipsec_bin = _strongswan_binary()
    if ipsec_bin:
        try:
            if os.path.basename(ipsec_bin) == 'swanctl':
                res = run(
                    [ipsec_bin, '--list-sas', '--ike', f'nm-{profile_id}'],
                    stdout=PIPE,
                    stderr=PIPE,
                    universal_newlines=True,
                    check=False,
                )
            else:
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
            '    forceencaps=yes',
            '    leftprotoport=17/%any',
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

    # Also generate modern swanctl configuration
    try:
        _write_swanctl_config(profile_id, cfg)
    except OSError:
        pass


def _ensure_swanctl_includes():
    """Ensure StrongSwan swanctl directory and main swanctl.conf includes conf.d/*.conf."""
    os.makedirs(SWANCTL_CONF_DIR, exist_ok=True)
    inc_line = 'include conf.d/*.conf'
    if os.path.isfile(SWANCTL_MAIN_CONF):
        try:
            with open(SWANCTL_MAIN_CONF, 'r', encoding='utf-8') as fh:
                content = fh.read()
            if inc_line not in content and 'conf.d/*.conf' not in content:
                with open(SWANCTL_MAIN_CONF, 'a', encoding='utf-8') as fh:
                    fh.write(f'\n{inc_line}\n')
        except OSError:
            pass
    else:
        try:
            with open(SWANCTL_MAIN_CONF, 'w', encoding='utf-8') as fh:
                fh.write(f'# Generated by NetworkMgr\n{inc_line}\n')
        except OSError:
            pass


def _write_swanctl_config(profile_id, cfg):
    """Write modern swanctl configuration file for profile_id."""
    _ensure_swanctl_includes()
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

    psk = _escape_quoted(cfg.get('psk', ''))
    user = _escape_quoted(cfg.get('username', '').strip())
    pw = _escape_quoted(cfg.get('password', ''))

    conn_lines = []
    secrets_lines = []

    if protocol == 'l2tp-ipsec':
        conn_lines = [
            'connections {',
            f'    nm-{profile_id} {{',
            '        version = 1',
            f'        remote_addrs = {gateway}',
            f'        proposals = {ike}',
            '        encap = yes',
            '        local {',
            '            auth = psk',
        ]
        if local_id:
            conn_lines.append(f'            id = "{local_id}"')
        conn_lines.extend([
            '        }',
            '        remote {',
            '            auth = psk',
            f'            id = "{remote_id}"' if remote_id else '            id = %any',
            '        }',
            '        children {',
            f'            nm-{profile_id} {{',
            '                mode = transport',
            f'                esp_proposals = {esp}',
            '                local_ts = dynamic[udp]',
            f'                remote_ts = dynamic[udp/{port}]',
            '                dpd_action = clear',
            '                start_action = none',
            '            }',
            '        }',
            '    }',
            '}',
        ])
        secrets_lines = [
            'secrets {',
            f'    ike-nm-{profile_id} {{',
            f'        id-1 = {gateway}',
            f'        id-2 = "{remote_id}"' if remote_id else '        id-2 = %any',
            f'        secret = "{psk}"',
            '    }',
            '}',
        ]
    elif protocol == 'ikev2-psk':
        conn_lines = [
            'connections {',
            f'    nm-{profile_id} {{',
            '        version = 2',
            f'        remote_addrs = {gateway}',
            f'        proposals = {ike}',
            '        vips = 0.0.0.0',
            '        local {',
            '            auth = psk',
        ]
        if local_id:
            conn_lines.append(f'            id = "{local_id}"')
        conn_lines.extend([
            '        }',
            '        remote {',
            '            auth = psk',
            f'            id = "{remote_id}"' if remote_id else '            id = %any',
            '        }',
            '        children {',
            f'            nm-{profile_id} {{',
            '                mode = tunnel',
            f'                esp_proposals = {esp}',
            '                remote_ts = 0.0.0.0/0',
            '                dpd_action = clear',
            '                start_action = none',
            '            }',
            '        }',
            '    }',
            '}',
        ])
        secrets_lines = [
            'secrets {',
            f'    ike-nm-{profile_id} {{',
            f'        id-1 = {gateway}',
            f'        id-2 = "{remote_id}"' if remote_id else '        id-2 = %any',
            f'        secret = "{psk}"',
            '    }',
            '}',
        ]
    elif protocol == 'ikev2-cert':
        ucert = _escape_quoted(cfg.get('user_cert', '').strip())
        cacert = _escape_quoted(cfg.get('ca_cert', '').strip())
        pkey = _escape_quoted(cfg.get('private_key', '').strip())
        key_pw = _escape_quoted(cfg.get('private_key_password', ''))
        conn_lines = [
            'connections {',
            f'    nm-{profile_id} {{',
            '        version = 2',
            f'        remote_addrs = {gateway}',
            f'        proposals = {ike}',
            '        vips = 0.0.0.0',
            '        local {',
            '            auth = pubkey',
        ]
        if ucert:
            conn_lines.append(f'            certs = "{ucert}"')
        if local_id:
            conn_lines.append(f'            id = "{local_id}"')
        conn_lines.extend([
            '        }',
            '        remote {',
            '            auth = pubkey',
            f'            id = "{remote_id}"' if remote_id else '            id = %any',
        ])
        if cacert:
            conn_lines.append(f'            cacerts = "{cacert}"')
        conn_lines.extend([
            '        }',
            '        children {',
            f'            nm-{profile_id} {{',
            '                mode = tunnel',
            f'                esp_proposals = {esp}',
            '                remote_ts = 0.0.0.0/0',
            '                dpd_action = clear',
            '                start_action = none',
            '            }',
            '        }',
            '    }',
            '}',
        ])
        if pkey:
            secrets_lines = [
                'secrets {',
                f'    rsa-nm-{profile_id} {{',
                f'        file = "{pkey}"',
            ]
            if key_pw:
                secrets_lines.append(f'        secret = "{key_pw}"')
            secrets_lines.extend(['    }', '}'])
    elif protocol == 'ikev1-xauth':
        conn_lines = [
            'connections {',
            f'    nm-{profile_id} {{',
            '        version = 1',
            f'        remote_addrs = {gateway}',
            f'        proposals = {ike}',
            '        vips = 0.0.0.0',
        ]
        if cfg.get('aggressive'):
            conn_lines.append('        aggressive = yes')
        conn_lines.extend([
            '        local {',
            '            auth = psk',
        ])
        if user:
            conn_lines.append(f'            xauth_id = "{user}"')
        if local_id:
            conn_lines.append(f'            id = "{local_id}"')
        conn_lines.extend([
            '        }',
            '        remote {',
            '            auth = psk',
            f'            id = "{remote_id}"' if remote_id else '            id = %any',
            '        }',
            '        children {',
            f'            nm-{profile_id} {{',
            '                mode = tunnel',
            f'                esp_proposals = {esp}',
            '                remote_ts = 0.0.0.0/0',
            '                dpd_action = clear',
            '                start_action = none',
            '            }',
            '        }',
            '    }',
            '}',
        ])
        secrets_lines = [
            'secrets {',
            f'    ike-nm-{profile_id} {{',
            f'        id-1 = {gateway}',
            f'        id-2 = "{remote_id}"' if remote_id else '        id-2 = %any',
            f'        secret = "{psk}"',
            '    }',
        ]
        if user:
            secrets_lines.extend([
                f'    xauth-nm-{profile_id} {{',
                f'        id = "{user}"',
                f'        secret = "{pw}"',
                '    }',
            ])
        secrets_lines.append('}')
    else:  # ikev2-eap
        cacert = _escape_quoted(cfg.get('ca_cert', '').strip())
        conn_lines = [
            'connections {',
            f'    nm-{profile_id} {{',
            '        version = 2',
            f'        remote_addrs = {gateway}',
            f'        proposals = {ike}',
            '        vips = 0.0.0.0',
            '        local {',
            '            auth = eap-mschapv2',
        ]
        if user:
            conn_lines.append(f'            eap_id = "{user}"')
        if local_id:
            conn_lines.append(f'            id = "{local_id}"')
        conn_lines.extend([
            '        }',
            '        remote {',
            '            auth = pubkey',
            f'            id = "{remote_id}"' if remote_id else '            id = %any',
        ])
        if cacert:
            conn_lines.append(f'            cacerts = "{cacert}"')
        conn_lines.extend([
            '        }',
            '        children {',
            f'            nm-{profile_id} {{',
            '                mode = tunnel',
            f'                esp_proposals = {esp}',
            '                remote_ts = 0.0.0.0/0',
            '                dpd_action = clear',
            '                start_action = none',
            '            }',
            '        }',
            '    }',
            '}',
        ])
        secrets_lines = [
            'secrets {',
            f'    eap-nm-{profile_id} {{',
            f'        id = "{user}"',
            f'        secret = "{pw}"',
            '    }',
            '}',
        ]

    content = '\n'.join(conn_lines + [''] + secrets_lines) + '\n'
    dest_path = os.path.join(SWANCTL_CONF_DIR, f'nm-{profile_id}.conf')
    _write_secure_ipsec_file(dest_path, content, 0o600)
    return dest_path


def _write_mpd5_config(profile_id, cfg):
    """Write the FreeBSD `mpd5` L2TP client configuration for `profile_id`."""
    profile_id = sanitize_ipsec_id(profile_id)
    mpd_dir = os.path.join(RUN_DIR, profile_id)
    os.makedirs(mpd_dir, exist_ok=True)
    try:
        os.chmod(mpd_dir, 0o700)
    except OSError:
        pass

    info_file = os.path.join(mpd_dir, 'up.info')
    up_script = os.path.join(mpd_dir, 'up.sh')
    down_script = os.path.join(mpd_dir, 'down.sh')

    # Create up.sh script to capture interface, assigned local IP, and peer/gateway IP
    up_sh_content = '\n'.join([
        '#!/bin/sh',
        f'echo "interface=$1" > "{info_file}"',
        f'echo "proto=$2" >> "{info_file}"',
        f'echo "local_ip=$3" >> "{info_file}"',
        f'echo "remote_ip=$4" >> "{info_file}"',
        f'echo "authname=$5" >> "{info_file}"',
        f'echo "dns1=$6" >> "{info_file}"',
        f'echo "dns2=$7" >> "{info_file}"',
        'exit 0',
        '',
    ])
    _write_secure_ipsec_file(up_script, up_sh_content, 0o755)

    # Create down.sh script
    state_file = os.path.join(RUN_DIR, f'{profile_id}.state')
    down_sh_content = '\n'.join([
        '#!/bin/sh',
        f'rm -f "{info_file}"',
        f'rm -f "{state_file}"',
        'exit 0',
        '',
    ])
    _write_secure_ipsec_file(down_script, down_sh_content, 0o755)

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
        '    set iface enable tcpmssfix',
        f'    set iface mtu {mtu}',
        f'    set iface up-script "{up_script}"',
        f'    set iface down-script "{down_script}"',
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
            gw4 = _clean_line(cfg.get('ipv4_gateway') or '')
            if gw4:
                gw4_ip = str(IPv4Address(gw4))
                ipcp_range = f'{addr4}/32 {gw4_ip}/32'
            else:
                ipcp_range = f'{addr4}/32 0.0.0.0/0'
        except ValueError:
            pass

    auth_lines = ['    set link no pap chap-md5 chap-msv1 chap-msv2 eap']
    accepted_auth = []
    if cfg.get('ppp_mschapv2', True):
        accepted_auth.append('chap-msv2')
    if cfg.get('ppp_chap', True):
        for proto in ('chap-md5', 'chap-msv1'):
            if proto not in accepted_auth:
                accepted_auth.append(proto)
    if cfg.get('ppp_pap', False):
        accepted_auth.append('pap')

    if not accepted_auth:
        accepted_auth.append('chap-msv2')

    for proto in accepted_auth:
        auth_lines.append(f'    set link accept {proto}')

    ccp_lines = [
        '    set bundle enable compression',
        '    set bundle enable crypt-reqd' if cfg.get('mppe_required', False) else '    set bundle disable crypt-reqd',
        '    set ccp yes mppc',
        '    set mppc yes e40 e128 stateless',
    ]

    mpd_conf = '\n'.join([
        'startup:',
        '    log +all -echo',
        '',
        'default:',
        '    load l2tp_client',
        '',
        'l2tp_client:',
        '    create bundle static B1',
        *iface_lines,
        '    set ipcp no vjcomp',
        '    set ipcp ranges ' + ipcp_range,
        '    set ipcp enable req-pri-dns req-sec-dns',
        *ccp_lines,
        '    create link static L1 l2tp',
        '    set link action bundle B1',
        f'    set link mtu {mtu}',
        f'    set link mru {mtu}',
        '    set link keep-alive 20 75',
        '    set link max-redial -1',
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


def _extract_recent_mpd_error(ident):
    """Scan syslog / mpd log files for recent error lines regarding this profile."""
    log_candidates = (
        '/var/log/mpd.log',
        '/var/log/messages',
        '/var/log/daemon.log',
        '/var/log/syslog',
    )
    for log_path in log_candidates:
        if os.path.isfile(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8', errors='replace') as fh:
                    lines = fh.readlines()[-300:]
                matched = [
                    l.strip()
                    for l in lines
                    if (ident in l or 'mpd' in l.lower())
                ]
                if matched:
                    log_debug('[IPsec] Recent mpd daemon logs:\n  ' + '\n  '.join(matched[-25:]))
                for l in reversed(matched):
                    lower = l.lower()
                    if any(
                        term in lower
                        for term in (
                            'auth failed',
                            'failed',
                            'error',
                            'rejected',
                            'refused',
                            'timed out',
                            'denied',
                            'no response',
                            'terminated',
                            'not converging',
                            'address already in use',
                        )
                    ):
                        return l
            except OSError:
                pass
    return ''


def _get_physical_default_gateway():
    """Find the current physical IPv4 default gateway IP and interface from netstat."""
    for args in (['netstat', '-rn', '-f', 'inet'], ['netstat', '-rn']):
        try:
            res = run(args, stdout=PIPE, stderr=PIPE, universal_newlines=True, check=False)
            if res.returncode == 0 and res.stdout:
                for line in res.stdout.splitlines():
                    parts = line.split()
                    if not parts:
                        continue
                    if parts[0] in ('default', '0.0.0.0'):
                        if len(parts) >= 2 and parts[1] not in ('default', '0.0.0.0'):
                            gw = parts[1]
                            iface = parts[3] if len(parts) > 3 and parts[2].startswith('UG') and not parts[3].startswith('UG') else parts[-1]
                            return gw, iface
        except OSError:
            pass
    return None, None


def _resolve_ipv4(host):
    """Resolve a hostname or IP string to an IPv4 address string."""
    clean_host = _clean_line(host)
    if not clean_host:
        return ''
    try:
        return str(IPv4Address(clean_host))
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(clean_host, None, socket.AF_INET)
        if infos:
            return infos[0][4][0]
    except (socket.gaierror, OSError):
        pass
    return ''


def _apply_custom_routes(cfg, fallback_gw=''):
    """Apply validated static IPv4/IPv6 routes configured on the profile."""
    for rt in cfg.get('ipv4_routes') or []:
        addr = _clean_line(rt.get('address') or '')
        mask = _clean_line(rt.get('netmask') or '')
        gw = _clean_line(rt.get('gateway') or cfg.get('ipv4_gateway') or fallback_gw or '')
        if addr and mask and gw:
            try:
                gw_ok = str(IPv4Address(gw))
                net_obj = IPv4Network(f'{addr}/{mask}', strict=False)
                run(
                    ['route', '-n', 'add', '-net', net_obj.with_prefixlen, gw_ok],
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


def _remove_custom_routes(cfg, fallback_gw=''):
    """Remove static IPv4/IPv6 routes on disconnect."""
    for rt in cfg.get('ipv4_routes') or []:
        addr = _clean_line(rt.get('address') or '')
        mask = _clean_line(rt.get('netmask') or '')
        gw = _clean_line(rt.get('gateway') or cfg.get('ipv4_gateway') or fallback_gw or '')
        if addr and mask and gw:
            try:
                gw_ok = str(IPv4Address(gw))
                net_obj = IPv4Network(f'{addr}/{mask}', strict=False)
                run(
                    ['route', '-n', 'delete', '-net', net_obj.with_prefixlen, gw_ok],
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
                    ['route', '-n', 'delete', '-inet6', net6_ok, gw6_ok],
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
        log_error(f'[IPsec] Configuration file not found: {conf_path}')
        return False, f'Configuration not found: {conf_path}'

    try:
        cfg = parse_ipsec_config(conf_path)
    except ValueError as err:
        log_error(f'[IPsec] Failed to parse config {conf_path}: {err}')
        return False, str(err)

    protocol = cfg.get('protocol', 'l2tp-ipsec')
    gateway = cfg.get('gateway', '')
    log_info(f'[IPsec] Initiating connection for "{profile_id}" (protocol={protocol}, gateway={gateway})')

    if not is_ipsec_installed(protocol):
        msg = ipsec_missing_packages_message(protocol)
        log_error(f'[IPsec] Missing required packages: {msg}')
        return False, msg

    os.makedirs(RUN_DIR, exist_ok=True)

    # Pin the VPN gateway host route to the physical default gateway so that
    # any VPN routes (default route 0.0.0.0/0 or subnets covering the server)
    # never hijack the outer tunnel packets (UDP 500/4500/1701).
    gw_host = cfg.get('gateway', '')
    gw_ip = _resolve_ipv4(gw_host)
    phys_gw, _ = _get_physical_default_gateway()
    if gw_ip and phys_gw and gw_ip != phys_gw:
        log_debug(f'[IPsec] Pinning VPN gateway route: route -n add -host {gw_ip} {phys_gw}')
        run(['route', '-n', 'add', '-host', gw_ip, phys_gw], stdout=PIPE, stderr=PIPE, check=False)
        endpoint_file = os.path.join(RUN_DIR, f'{profile_id}.endpoint')
        try:
            with open(endpoint_file, 'w', encoding='utf-8') as fh:
                fh.write(f'{gw_ip}\n{phys_gw}\n')
        except OSError:
            pass

    _write_strongswan_files(profile_id, cfg)
    log_debug(f'[IPsec] StrongSwan configuration files generated for "{profile_id}"')

    ipsec_bin = _strongswan_binary()
    is_swanctl = (os.path.basename(ipsec_bin) == 'swanctl') if ipsec_bin else False

    try:
        if is_swanctl:
            log_debug(f'[IPsec] Using swanctl backend ({ipsec_bin})')
            # Check if charon daemon is responding
            status_rc, _ = _run_daemon_cmd([ipsec_bin, '--stats'], timeout=5)
            if status_rc != 0:
                log_debug(f'[IPsec] StrongSwan daemon not running; executing service strongswan onestart...')
                _run_daemon_cmd(['service', 'strongswan', 'onestart'], timeout=10)
                sleep(1.0)
                status_rc, _ = _run_daemon_cmd([ipsec_bin, '--stats'], timeout=5)
                if status_rc != 0:
                    _run_daemon_cmd(['service', 'strongswan', 'start'], timeout=10)
                    sleep(1.0)

            log_debug(f'[IPsec] Loading swanctl configurations and secrets: {ipsec_bin} --load-all...')
            load_rc, load_out = _run_daemon_cmd([ipsec_bin, '--load-all'], timeout=10)
            if load_rc != 0:
                log_warning(f'[IPsec] swanctl --load-all returned rc={load_rc}: {load_out}')

            log_debug(f'[IPsec] Establishing IPsec SA: {ipsec_bin} --initiate --child nm-{profile_id}...')
            up_rc, output_text = _run_daemon_cmd(
                [ipsec_bin, '--initiate', '--child', f'nm-{profile_id}', '--timeout', '25'],
                timeout=30,
            )
            log_debug(f'[IPsec] swanctl initiate output (rc={up_rc}):\n{output_text}')
            lower_out = output_text.lower()
            if up_rc != 0 or ('completed successfully' not in lower_out and 'established' not in lower_out):
                err_msg = output_text.strip() or 'swanctl failed to establish IPsec SA.'
                log_error(f'[IPsec] swanctl SA failed: {err_msg}')
                disable_ipsec(profile_id)
                return False, err_msg
            log_info(f'[IPsec] swanctl IPsec SA established successfully')

        else:
            log_debug(f'[IPsec] Using legacy ipsec backend ({ipsec_bin})')
            # Ensure strongSwan charon/starter is running and reload configs
            status_rc, _ = _run_daemon_cmd([ipsec_bin, 'status'], timeout=5)
            if status_rc != 0:
                log_debug(f'[IPsec] StrongSwan daemon not running; executing {ipsec_bin} start...')
                _run_daemon_cmd([ipsec_bin, 'start'], timeout=10)
                sleep(1.0)
            else:
                log_debug(f'[IPsec] Reloading StrongSwan secrets and connections...')
                _run_daemon_cmd([ipsec_bin, 'reload'], timeout=5)
                _run_daemon_cmd([ipsec_bin, 'rereadsecrets'], timeout=5)
                sleep(0.4)

            log_debug(f'[IPsec] Establishing IPsec SA: {ipsec_bin} up nm-{profile_id}...')
            up_rc, output_text = _run_daemon_cmd(
                [ipsec_bin, 'up', f'nm-{profile_id}'],
                timeout=20,
            )
            log_debug(f'[IPsec] StrongSwan up output (rc={up_rc}):\n{output_text}')
            if up_rc != 0 and 'established' not in output_text.lower():
                err_msg = output_text.strip() or 'StrongSwan failed to establish IPsec SA.'
                log_error(f'[IPsec] StrongSwan SA failed: {err_msg}')
                disable_ipsec(profile_id)
                return False, err_msg
            log_info(f'[IPsec] StrongSwan IPsec SA established successfully')
    except OSError as exc:
        log_error(f'[IPsec] OS error invoking StrongSwan: {exc}')
        disable_ipsec(profile_id)
        return False, str(exc)

    assigned_iface = ''
    assigned_ip = ''
    remote_gw = ''

    if protocol == 'l2tp-ipsec':
        mpd_bin = _mpd5_binary()
        mpd_dir = _write_mpd5_config(profile_id, cfg)
        log_debug(f'[IPsec] Generated mpd5 configuration in {mpd_dir}/mpd.conf')
        pid_file = os.path.join(RUN_DIR, f'{profile_id}.pid')
        state_file = os.path.join(RUN_DIR, f'{profile_id}.state')
        info_file = os.path.join(mpd_dir, 'up.info')

        # Clean up stale pid / state / info files
        for stale in (pid_file, state_file, info_file):
            if os.path.exists(stale):
                try:
                    os.remove(stale)
                except OSError:
                    pass

        ident = f'networkmgr_{profile_id}'
        log_debug(f'[IPsec] Launching mpd5 daemon: {mpd_bin} -b -d {mpd_dir} -p {pid_file} -s {ident} l2tp_client')
        try:
            mpd_rc, err = _run_daemon_cmd(
                [
                    mpd_bin,
                    '-b',
                    '-d', mpd_dir,
                    '-p', pid_file,
                    '-s', ident,
                    'l2tp_client',
                ],
                timeout=10,
            )
            if mpd_rc not in (0, None):
                disable_ipsec(profile_id)
                err_msg = (err or 'mpd5 failed to start L2TP session.').strip()
                log_error(f'[IPsec] mpd5 start error: {err_msg}')
                return False, err_msg
        except Exception as exc:
            disable_ipsec(profile_id)
            log_error(f'[IPsec] Exception spawning mpd5: {exc}')
            return False, str(exc)

        # Monitor mpd5: wait for PID file and confirm process starts
        log_debug(f'[IPsec] Monitoring mpd5 PID file and process table...')
        mpd_running = False
        mpd_pid = None
        for _ in range(30):  # up to 3 seconds (30 * 0.1s)
            sleep(0.1)
            if os.path.isfile(pid_file):
                try:
                    with open(pid_file, 'r', encoding='utf-8') as fh:
                        pid_val = int(fh.read().strip())
                    if _pid_is_mpd5(pid_val):
                        mpd_pid = pid_val
                        mpd_running = True
                        break
                except (ValueError, OSError):
                    pass

        if not mpd_running:
            err_msg = _extract_recent_mpd_error(ident) or 'mpd5 failed to start or write PID.'
            log_error(f'[IPsec] mpd5 did not start cleanly: {err_msg}')
            disable_ipsec(profile_id)
            return False, err_msg

        # Poll for link & IPCP address negotiation (up to 20 seconds)
        log_debug(f'[IPsec] mpd5 running (PID={mpd_pid}). Waiting for IPCP address assignment...')
        acquired_ip = False
        for _ in range(200):  # 20.0 seconds (200 * 0.1s)
            sleep(0.1)
            if not _pid_is_mpd5(mpd_pid):
                err_msg = (
                    _extract_recent_mpd_error(ident)
                    or 'mpd5 L2TP session closed unexpectedly. Verify user credentials, IPsec PSK, and PPP auth settings.'
                )
                log_error(f'[IPsec] mpd5 died during PPP handshake: {err_msg}')
                disable_ipsec(profile_id)
                return False, err_msg

            if os.path.isfile(info_file):
                try:
                    with open(info_file, 'r', encoding='utf-8') as fh:
                        info_content = fh.read()
                    props = dict(line.split('=', 1) for line in info_content.splitlines() if '=' in line)
                    assigned_iface = props.get('interface', '')
                    assigned_ip = props.get('local_ip', '')
                    remote_gw = props.get('remote_ip', '')
                    if assigned_ip and assigned_ip != '0.0.0.0':
                        acquired_ip = True
                        break
                except (OSError, ValueError):
                    pass

        if not acquired_ip:
            # Fallback: check if an ng* interface has an assigned inet address
            try:
                if_res = run(['ifconfig'], stdout=PIPE, stderr=PIPE, universal_newlines=True, check=False)
                for block in re.split(r'\n(?=[a-zA-Z0-9_]+:)', if_res.stdout or ''):
                    if block.startswith('ng'):
                        match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)\s+-->\s+(\d+\.\d+\.\d+\.\d+)', block)
                        if match:
                            assigned_ip = match.group(1)
                            remote_gw = match.group(2)
                            acquired_ip = True
                            assigned_iface = block.split(':', 1)[0]
                            break
            except OSError:
                pass

        if not acquired_ip:
            err_msg = (
                _extract_recent_mpd_error(ident)
                or 'mpd5 connected to L2TP server, but failed to acquire IPv4 address via IPCP. Verify server IP pool, DNS, and IPCP settings.'
            )
            log_error(f'[IPsec] IPCP negotiation failed: {err_msg}')
            disable_ipsec(profile_id)
            return False, err_msg

        log_info(f'[IPsec] mpd5 L2TP session established: interface={assigned_iface}, local_ip={assigned_ip}, remote_gw={remote_gw} (PID={mpd_pid})')

    state_file = os.path.join(RUN_DIR, f'{profile_id}.state')
    try:
        with open(state_file, 'w', encoding='utf-8') as fh:
            fh.write(
                f'connected\n'
                f'interface={assigned_iface}\n'
                f'ip={assigned_ip}\n'
                f'gateway={remote_gw}\n'
            )
    except OSError:
        pass

    log_debug(f'[IPsec] Applying static routes if configured...')
    _apply_custom_routes(cfg, fallback_gw=remote_gw)
    log_info(f'[IPsec] Connection "{profile_id}" successfully established')
    return True, ''


def disable_ipsec(profile_id):
    """Stop an active IPsec or L2TP/IPsec connection."""
    profile_id = sanitize_ipsec_id(profile_id)
    log_info(f'[IPsec] Disconnecting IPsec/L2TP connection "{profile_id}"...')
    mpd_dir = os.path.join(RUN_DIR, profile_id)
    info_file = os.path.join(mpd_dir, 'up.info')
    if os.path.isfile(info_file):
        try:
            os.remove(info_file)
        except OSError:
            pass

    pid_file = os.path.join(RUN_DIR, f'{profile_id}.pid')
    if os.path.isfile(pid_file):
        try:
            with open(pid_file, 'r', encoding='utf-8') as fh:
                pid_str = fh.read().strip()
            if pid_str.isdigit() and _pid_is_mpd5(int(pid_str)):
                log_debug(f'[IPsec] Terminating mpd5 process (PID={pid_str})...')
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
            if os.path.basename(ipsec_bin) == 'swanctl':
                log_debug(f'[IPsec] Bringing down swanctl IKE SA: {ipsec_bin} --terminate --ike nm-{profile_id}...')
                run(
                    [ipsec_bin, '--terminate', '--ike', f'nm-{profile_id}'],
                    stdout=PIPE,
                    stderr=PIPE,
                    check=False,
                )
            else:
                log_debug(f'[IPsec] Bringing down StrongSwan SA: {ipsec_bin} down nm-{profile_id}...')
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

    endpoint_file = os.path.join(RUN_DIR, f'{profile_id}.endpoint')
    if os.path.isfile(endpoint_file):
        try:
            with open(endpoint_file, 'r', encoding='utf-8') as fh:
                ep_lines = [l.strip() for l in fh.readlines() if l.strip()]
            if len(ep_lines) >= 2:
                gw_ip, phys_gw = ep_lines[0], ep_lines[1]
                log_debug(f'[IPsec] Removing pinned VPN gateway route: route -n delete -host {gw_ip} {phys_gw}')
                run(['route', '-n', 'delete', '-host', gw_ip, phys_gw], stdout=PIPE, stderr=PIPE, check=False)
        except OSError:
            pass
        try:
            os.remove(endpoint_file)
        except OSError:
            pass

    conf_path = os.path.join(IPSEC_DIR, f'{profile_id}.conf')
    if os.path.isfile(conf_path):
        try:
            cfg = parse_ipsec_config(conf_path)
            _remove_custom_routes(cfg)
        except Exception:
            pass

    log_info(f'[IPsec] Connection "{profile_id}" is disconnected')
