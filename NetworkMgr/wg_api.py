#!/usr/bin/env python

"""WireGuard tunnel discovery and control.

Lists the tunnel configurations under $PREFIX/etc/wireguard, reports which
are running, and brings them up or down through the wireguard rc service.
"""

import os
import re
import sys
from platform import system
from subprocess import PIPE, run

PREFIX = '/usr/local' if system() in ('FreeBSD', 'MidnightBSD', 'DragonFly') else sys.prefix
WG_CONFIG_PATH = f'{PREFIX}/etc/wireguard/'
WG_ID_REGEX = re.compile(r'[^A-Za-z0-9_-]+')


def sanitize_wg_id(name):
    """Turn a display name or filename into a safe WireGuard tunnel name."""
    cleaned = WG_ID_REGEX.sub('_', name.strip()).strip('_-')
    return cleaned[:15] or 'wg0'


def default_wireguard_config(name='wg0'):
    """Return a fresh WireGuard configuration dictionary."""
    return {
        'vpn_type': 'wireguard',
        'name': name,
        'profile_id': sanitize_wg_id(name),
        'private_key': '',
        'address': '',
        'dns': '',
        'mtu': '',
        'listen_port': '',
        'table': '',
        'pre_up': '',
        'post_up': '',
        'pre_down': '',
        'post_down': '',
        'public_key': '',
        'preshared_key': '',
        'endpoint': '',
        'allowed_ips': '0.0.0.0/0, ::/0',
        'persistent_keepalive': '',
    }


def parse_wireguard_config(filepath):
    """Parse a WireGuard (.conf) file into a dictionary for the VPN editor.

    Args:
        filepath (str): path to the WireGuard .conf file.

    Returns:
        dict: structured WireGuard configuration.
    """
    if not os.path.isfile(filepath):
        raise ValueError(f'File not found: "{filepath}"')

    stem = os.path.splitext(os.path.basename(filepath))[0]
    cfg = default_wireguard_config(stem)
    cfg['allowed_ips'] = ''
    section = None

    try:
        with open(filepath, 'r', encoding='utf-8-sig', errors='replace') as handle:
            lines = handle.readlines()
    except OSError as exc:
        raise ValueError(f'Could not read "{filepath}": {exc}') from exc

    addresses = []
    dns_list = []
    allowed_list = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith('#'):
            if line.startswith('# Name ='):
                custom = line.split('=', 1)[1].strip()
                if custom:
                    cfg['name'] = custom
            continue

        sec_match = re.match(r'^\[([A-Za-z]+)\]$', line)
        if sec_match:
            section = sec_match.group(1).lower()
            continue

        if '=' not in line:
            continue
        key, val = line.split('=', 1)
        key = key.strip().lower()
        val = val.strip()

        if section == 'interface':
            if key == 'privatekey':
                cfg['private_key'] = val
            elif key == 'address':
                addresses.append(val)
            elif key == 'dns':
                dns_list.append(val)
            elif key == 'mtu':
                cfg['mtu'] = val
            elif key == 'listenport':
                cfg['listen_port'] = val
            elif key == 'table':
                cfg['table'] = val
            elif key == 'preup':
                cfg['pre_up'] = val
            elif key == 'postup':
                cfg['post_up'] = val
            elif key == 'predown':
                cfg['pre_down'] = val
            elif key == 'postdown':
                cfg['post_down'] = val
        elif section == 'peer':
            if key == 'publickey':
                cfg['public_key'] = val
            elif key == 'presharedkey':
                cfg['preshared_key'] = val
            elif key == 'endpoint':
                cfg['endpoint'] = val
            elif key == 'allowedips':
                allowed_list.append(val)
            elif key == 'persistentkeepalive':
                cfg['persistent_keepalive'] = val

    if addresses:
        cfg['address'] = ', '.join(addresses)
    if dns_list:
        cfg['dns'] = ', '.join(dns_list)
    if allowed_list:
        cfg['allowed_ips'] = ', '.join(allowed_list)

    return cfg


def save_wireguard_config(cfg):
    """Save a WireGuard configuration to /usr/local/etc/wireguard/<id>.conf.

    Args:
        cfg (dict): structured WireGuard configuration dictionary.

    Returns:
        str: the saved tunnel profile_id.
    """
    display_name = cfg.get('name', '').strip()
    if not display_name:
        raise ValueError('Connection name is required.')
    profile_id = sanitize_wg_id(cfg.get('profile_id') or display_name)
    if not cfg.get('private_key', '').strip():
        raise ValueError('Interface Private Key is required.')
    if not cfg.get('public_key', '').strip():
        raise ValueError('Peer Public Key is required.')

    os.makedirs(WG_CONFIG_PATH, exist_ok=True)
    lines = [
        f'# Name = {display_name}',
        '[Interface]',
        f"PrivateKey = {cfg['private_key'].strip()}",
    ]
    if cfg.get('address', '').strip():
        lines.append(f"Address = {cfg['address'].strip()}")
    if cfg.get('dns', '').strip():
        lines.append(f"DNS = {cfg['dns'].strip()}")
    if cfg.get('listen_port', '').strip():
        lines.append(f"ListenPort = {cfg['listen_port'].strip()}")
    if cfg.get('mtu', '').strip():
        lines.append(f"MTU = {cfg['mtu'].strip()}")
    if cfg.get('table', '').strip():
        lines.append(f"Table = {cfg['table'].strip()}")
    if cfg.get('pre_up', '').strip():
        lines.append(f"PreUp = {cfg['pre_up'].strip()}")
    if cfg.get('post_up', '').strip():
        lines.append(f"PostUp = {cfg['post_up'].strip()}")
    if cfg.get('pre_down', '').strip():
        lines.append(f"PreDown = {cfg['pre_down'].strip()}")
    if cfg.get('post_down', '').strip():
        lines.append(f"PostDown = {cfg['post_down'].strip()}")

    lines.extend([
        '',
        '[Peer]',
        f"PublicKey = {cfg['public_key'].strip()}",
    ])
    if cfg.get('preshared_key', '').strip():
        lines.append(f"PresharedKey = {cfg['preshared_key'].strip()}")
    if cfg.get('endpoint', '').strip():
        lines.append(f"Endpoint = {cfg['endpoint'].strip()}")
    allowed = cfg.get('allowed_ips', '').strip() or '0.0.0.0/0, ::/0'
    lines.append(f'AllowedIPs = {allowed}')
    if cfg.get('persistent_keepalive', '').strip():
        lines.append(f"PersistentKeepalive = {cfg['persistent_keepalive'].strip()}")

    conf_file = os.path.join(WG_CONFIG_PATH, f'{profile_id}.conf')
    with open(conf_file, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')
    os.chmod(conf_file, 0o600)
    return profile_id


def delete_wireguard_config(wg_device):
    """Stop the WireGuard tunnel if running and delete its .conf file."""
    disable_wg(wg_device)
    conf_file = os.path.join(WG_CONFIG_PATH, f'{wg_device}.conf')
    if os.path.exists(conf_file):
        try:
            os.remove(conf_file)
        except OSError:
            pass


def wg_service_state():
    """Report whether rc is set to manage the WireGuard tunnels.

    Asked through sysrc rather than `service wireguard rcvar`, which answers
    the same question but wraps it in four lines of prose that have to be
    parsed, and quotes the value so every caller has to compare against
    '"NO"'. sysrc gives the bare value.

    Returns:
        str: 'YES' or 'NO'. A variable set nowhere reads as 'NO', which is
            the rc script's own default: line 69 of
            /usr/local/etc/rc.d/wireguard is `: ${wireguard_enable="NO"}`,
            and sysrc reports an unset variable as an error rather than a
            value.
    """
    result = run(['sysrc', '-n', 'wireguard_enable'],
                 stdout=PIPE, stderr=PIPE, check=False, text=True)
    if result.returncode != 0:
        return 'NO'
    return result.stdout.strip() or 'NO'


def wg_dictionary(service_state):
    """Collect the WireGuard tunnels and their state.

    The service state is passed in rather than read here. Asking rc for it
    costs about 13 ms of shell, against under 1 ms for everything else in
    this function, and `wireguard_enable` only changes when someone edits
    rc.conf. Reading it once and handing it down keeps the tray refresh
    cheap.

    Args:
        service_state (str): 'YES' or 'NO' from wg_service_state().

    Returns:
        dict: 'service' as given, 'default', and 'configs' mapping each
            tunnel device to its 'state' and its 'info' display name.
    """
    maindictionary = {
        'service': service_state,
        'default': '',
    }
    configs = {}

    if os.path.exists(WG_CONFIG_PATH):
        wgconfigs = sorted(os.listdir(WG_CONFIG_PATH))
        for wgconfig in wgconfigs:
            if not wgconfig.endswith('.conf'):
                continue
            full_path = os.path.join(WG_CONFIG_PATH, wgconfig)
            if not os.path.isfile(full_path):
                continue
            wg_device = wgconfig[:-5]
            wg_state = wg_status(wg_device)
            wg_name = wg_device
            endpoint = ''
            with open(full_path, encoding="utf-8", errors="replace") as content:
                for line in content:
                    if "# Name =" in line:
                        wg_name = line.split('=', 1)[1].strip() or wg_device
                    elif line.strip().lower().startswith('endpoint') and '=' in line:
                        endpoint = line.split('=', 1)[1].strip()

            seconddictionary = {
                'state': wg_state,
                'info': wg_name,
                'path': full_path,
                'gateway': endpoint,
            }
            configs[wg_device] = seconddictionary

    maindictionary['configs'] = configs
    return maindictionary


def disable_wg(wgconfig):
    """Take the specified WireGuard configuration (device) down.

    Args:
        wgconfig (str): the tunnel's configuration name, without .conf.
    """
    run(['wg-quick', 'down', wgconfig], check=False)


def enable_wg(wgconfig):
    """Bring the specified WireGuard configuration (device) up.

    Args:
        wgconfig (str): the tunnel's configuration name, without .conf.
    """
    run(['wg-quick', 'up', wgconfig], check=False)


def wg_status(wgconfig):
    """Function returning the WireGuard configuration (device) is connected or not."""
    result = run(['wg', 'show', wgconfig], stdout=PIPE, stderr=PIPE, check=False)
    out = result.stdout.decode('utf-8')
    error = result.stderr.decode('utf-8')

    if len(out) == 0 and 'Unable to access interface: Device not configured' in error:
        status = "Disconnected"
    else:
        status = "Connected"

    return status
