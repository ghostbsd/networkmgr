#!/usr/bin/env python

"""Network operations backing the tray icon and the configuration window.

Everything that reads or changes the system's network state lives here:
interface enumeration and status, the wpa_supplicant control-socket layer
(scanning, saved networks, connection state), the wpa_supplicant.conf
readers and writers, and the wired and wireless bring-up commands. Nothing
in this module touches GTK.
"""

from concurrent.futures import ThreadPoolExecutor
from subprocess import (
    DEVNULL,
    CalledProcessError,
    TimeoutExpired,
    run,
    check_output
)
import os
import re
from string import hexdigits
from time import monotonic, sleep


# EAP methods supported for enterprise WPA
EAP_METHODS = ['PEAP', 'TTLS', 'TLS', 'LEAP', 'FAST', 'PWD']

# Phase 2 (inner) authentication methods
PHASE2_METHODS = ['MSCHAPV2', 'GTC', 'PAP', 'CHAP', 'MD5']

# Matches a dotted-quad IPv4 address in ifconfig output.
IP_REGEX = r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+'

# Threads for one refresh pass. They wait on subprocesses, not the CPU.
_REFRESH_WORKERS = 6


def _run(*args, check=False):
    """
    Run a command without a shell and return the finished process.

    Args:
        *args (str): the program and its arguments, one word per argument.
        check (bool): raise CalledProcessError on a non-zero exit. Left False
            where a non-zero exit is a normal answer, such as asking about an
            interface that is not there.

    Returns:
        subprocess.CompletedProcess: with stdout and stderr captured as text.
    """
    return run(args, capture_output=True, text=True, check=check)


def _ifconfig(card):
    """
    Return the ifconfig output for one interface.

    Args:
        card (str): interface name, for instance em0 or wlan0.

    Returns:
        str: everything ifconfig printed, or an empty string when the
            interface does not exist.
    """
    return _run('ifconfig', card).stdout


def ifconfig_snapshot():
    """Read every interface's ifconfig output in a single call.

    One call, so every interface's state comes from the same instant.

    Returns:
        dict[str, str]: interface name mapped to its block of output.
    """
    return {
        match.group(1): match.group(0)
        for match in re.finditer(r'^(\w+):.*?(?=^\w+:|\Z)',
                                 _run('ifconfig').stdout, re.M | re.S)
    }


def card_has_address(ifconfig_text):
    """
    Report whether an interface has an IPv4 address.

    Args:
        ifconfig_text (str): that interface's block from ifconfig_snapshot().

    Returns:
        bool: True when ifconfig lists an inet address on the interface.
    """
    return 'inet ' in ifconfig_text


def default_card():
    """
    Return the interface that carries the default route.

    The routing table is filtered here rather than piped through grep, which
    is what used to require a shell.

    Returns:
        str or None: the interface name, or None when there is no default
            route at all.
    """
    for line in _run('netstat', '-rn').stdout.splitlines():
        if line.startswith('default'):
            fields = line.split()
            if len(fields) > 3:
                return fields[3]
    return None


def _is_disabled(ifconfig_text):
    """
    Report whether an interface has been administratively downed.

    The UP flag is the only reliable evidence. An empty scan list does not
    mean the card is off (net80211 flushes the cache on INIT), and a wired
    `status:` line describes the link, not the interface.

    Args:
        ifconfig_text (str): that interface's block from ifconfig_snapshot().

    Returns:
        bool: True when the UP flag is absent. False when the interface has
            no flags line at all, which means it is not there to be disabled.
    """
    flags = re.search(r'flags=\w+<([^>]*)>', ifconfig_text)
    if flags is None:
        return False
    return 'UP' not in flags.group(1).split(',')


def nics_list(snapshot=None):
    """
    List the interfaces networkmgr manages.

    Args:
        snapshot (dict or None): an ifconfig_snapshot() result to take the
            names from. Left None by callers that have no snapshot to hand,
            which then costs one `ifconfig -l`.

    Returns:
        list[str]: sorted interface names, with the virtual and tunnel
            devices such as lo, bridge, tun and wg removed.
    """
    not_nics_regex = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|" \
        r"faith|ppp|bridge|wg)[0-9]+(\s*)|vm-[a-z]+(\s*)"
    if snapshot is None:
        nics = _run('ifconfig', '-l').stdout.strip()
    else:
        nics = ' '.join(snapshot)
    return sorted(re.sub(not_nics_regex, '', nics).strip().split())


def card_has_carrier(ifconfig_text):
    """
    Report whether a wired interface has a cable in it.

    Args:
        ifconfig_text (str): that interface's block from ifconfig_snapshot().

    Returns:
        bool: True when ifconfig reports `status: active`, which is carrier
            and not the same question as whether the card has an address.
    """
    return 'status: active' in ifconfig_text


def bar_percent(level, noise):
    """
    Turn a signal and noise pair into the percentage the tray shows.

    Args:
        level (int): received signal strength in dBm, a negative number.
        noise (int): the radio's noise floor in dBm, also negative.

    Returns:
        int: a percentage, deliberately not clamped, matching the old
            ifconfig S:N arithmetic so the icons pick the same buckets.
    """
    return int((level - noise) * 4)


def get_system_ca_certificates():
    """
    Get list of available system CA certificate bundles on FreeBSD.
    """
    ca_paths = [
        '/etc/ssl/certs/ca-root-nss.crt',
        '/usr/local/share/certs/ca-root-nss.crt',
        '/etc/ssl/cert.pem',
    ]
    available = []
    for path in ca_paths:
        if os.path.exists(path):
            available.append(path)
    return available


def connected_signal(wifi_card):
    """
    Signal percentage of the access point this card is joined to.

    Reads the one BSS the card is on, so this does not depend on the scan
    table.

    Args:
        wifi_card (str): wireless interface name.

    Returns:
        int or None: the percentage, or None when the card is not joined to
            anything or the driver reports no level.
    """
    bss = _parse_key_values(wpa_cli(wifi_card, 'bss', 'current') or '')
    if bss.get('level') and bss.get('noise'):
        return bar_percent(int(bss['level']), int(bss['noise']))
    return None


def _wireless_state(ifconfig_text, status):
    """
    Describe what a wireless interface is doing.

    Connected means wpa_state=COMPLETED, the handshake finished. ifconfig's
    `associated` appears about three seconds earlier, before the card can
    pass traffic.

    Args:
        ifconfig_text (str): that interface's block from ifconfig_snapshot().
        status (dict): the wpa_status() result for the same interface, passed
            in so the daemon is asked once per refresh.

    Returns:
        dict: with 'connection' set to Disabled, Disconnected or Connected,
            and 'ssid' set only when connected.
    """
    if _is_disabled(ifconfig_text):
        return {'connection': 'Disabled', 'ssid': None}
    if status.get('wpa_state') == 'COMPLETED':
        return {'connection': 'Connected', 'ssid': status.get('ssid')}
    return {'connection': 'Disconnected', 'ssid': None}


def _wired_state(ifconfig_text):
    """
    Describe what a wired interface is doing.

    Args:
        ifconfig_text (str): that interface's block from ifconfig_snapshot().

    Returns:
        dict: with 'connection' set to Disabled when we downed the interface,
            Unplug when there is no cable, Connected when it holds an
            address, and Disconnected when it has carrier but no address.
    """
    if _is_disabled(ifconfig_text):
        return {'connection': 'Disabled'}
    if not card_has_carrier(ifconfig_text):
        return {'connection': 'Unplug'}
    if card_has_address(ifconfig_text):
        return {'connection': 'Connected'}
    return {'connection': 'Disconnected'}


def network_dictionary():
    """
    Collect everything the tray menu draws itself from.

    Every command runs here once and the results are handed down, rather
    than each reader fetching its own.

    Returns:
        dict: 'default' names the interface holding the default route.
            'cards' maps each interface to 'state' (see _wireless_state and
            _wired_state), 'signal' for signal, and the raw 'ifconfig' and
            'status' the state came from. No networks in range: that is
            scan_networks(), called when the submenu opens.
    """
    # Two waves: netstat runs alongside ifconfig, but the daemon queries
    # cannot start until ifconfig has said which cards are wireless.
    with ThreadPoolExecutor(max_workers=_REFRESH_WORKERS) as pool:
        default = pool.submit(default_card)
        snapshot = ifconfig_snapshot()

        interfaces = nics_list(snapshot)
        wireless = [c for c in interfaces if 'wlan' in c]
        statuses = {c: pool.submit(wpa_status, c) for c in wireless}
        signals = {c: pool.submit(connected_signal, c) for c in wireless}

        cards = {}
        for card in interfaces:
            ifconfig_text = snapshot.get(card, '')
            if card in statuses:
                status = statuses[card].result()
                state = _wireless_state(ifconfig_text, status)
                cards[card] = {
                    'state': state,
                    'signal': signals[card].result(),
                    'ifconfig': ifconfig_text,
                    'status': status,
                }
            else:
                cards[card] = {
                    'state': _wired_state(ifconfig_text),
                    'signal': None,
                    'ifconfig': ifconfig_text,
                    'status': {},
                }
        return {'default': default.result(), 'cards': cards}


def _inet_line(ifconfig_text):
    """
    Return an interface's IPv4 address line as ifconfig prints it.

    Args:
        ifconfig_text (str): that interface's block from ifconfig_snapshot().

    Returns:
        str: the whole `inet ...` line, or an empty string when the interface
            has no IPv4 address.
    """
    for line in ifconfig_text.splitlines():
        if line.strip().startswith('inet '):
            return line.strip()
    return ''


def tray_state():
    """
    Read only what the tray icon and its tooltip show.

    Deliberately narrower than network_dictionary(): one interface, up or
    not, and its signal from `bss current` rather than the scan table.

    Returns:
        dict: 'card' naming the interface holding the default route or None,
            'kind' being 'wifi', 'wire' or None, 'connection' as
            _wireless_state or _wired_state reports it, 'ssid' and 'signal'
            filled in for a connected wireless card, and 'tooltip' ready to
            display.
    """
    card = default_card()
    if card is None:
        return {'card': None, 'kind': None, 'connection': 'Disconnected',
                'ssid': None, 'signal': None,
                'tooltip': "Network card is not enabled"}

    wireless = 'wlan' in card
    if wireless:
        # Three independent reads, so they are worth running together.
        with ThreadPoolExecutor(max_workers=_REFRESH_WORKERS) as pool:
            text_job = pool.submit(_ifconfig, card)
            status_job = pool.submit(wpa_status, card)
            bss_job = pool.submit(wpa_cli, card, 'bss', 'current')
            ifconfig_text = text_job.result()
            status = status_job.result()
            bss = _parse_key_values(bss_job.result() or '')
    else:
        # A wired card needs one command, and a pool for one job costs more
        # than it saves.
        ifconfig_text = _ifconfig(card)
        status, bss = {}, {}

    if wireless:
        state = _wireless_state(ifconfig_text, status)
    else:
        state = _wired_state(ifconfig_text)

    signal = None
    if bss.get('level') and bss.get('noise'):
        signal = bar_percent(int(bss['level']), int(bss['noise']))

    inet = subnet_hex_to_dec(_inet_line(ifconfig_text))
    if wireless:
        if state['connection'] != 'Connected':
            tooltip = f"WiFi {card} not connected"
        else:
            detail = f"ssid {state['ssid']} bssid {status.get('bssid', '')}"
            tooltip = (f"Signal Strength: {signal if signal is not None else 0}% \n"
                       f"{detail} \n{inet}")
    else:
        tooltip = inet

    return {
        'card': card,
        'kind': 'wifi' if wireless else 'wire',
        'connection': state['connection'],
        'ssid': state.get('ssid'),
        'signal': signal,
        'tooltip': tooltip,
    }


def restart_all_nics(_widget):
    """Restart every network interface.

    Args:
        _widget (Gtk.Widget): the menu item that fired this, unused.
    """
    _run('service', 'netif', 'restart')


def stop_network_card(netcard):
    """Take one interface down.

    dhclient watches the routing socket, sees RTF_UP cleared and exits
    through its FAIL path, which deletes the address, deletes the routes and
    restores resolv.conf. A static card keeps its address, deliberately, so
    that bringing it back up needs nothing but the up.

    Handing the default route to another interface is devd's: the link
    going down fires src/auto-switch.py, which does exactly that.

    Args:
        netcard (str): interface name, for instance em0.
    """
    _run('ifconfig', netcard, 'down')


def restart_card_network(netcard):
    """Restart one interface through rc.

    Args:
        netcard (str): interface name, for instance em0.
    """
    _run('service', 'netif', 'restart', netcard)


def restart_routing_and_dhcp(netcard):
    """Rebuild the routing table, then renew the lease on one interface.

    Args:
        netcard (str): interface name to restart dhclient on.
    """
    _run('service', 'routing', 'restart')
    _run('service', 'dhclient', 'restart', netcard)


def start_static_network(netcard, inet, netmask):
    """Put a static IPv4 address on an interface and rebuild the routes.

    Args:
        netcard (str): interface name, for instance em0.
        inet (str): IPv4 address in dotted-decimal form.
        netmask (str): netmask in dotted-decimal form.
    """
    _run('ifconfig', netcard, 'inet', inet, 'netmask', netmask)
    _run('service', 'routing', 'restart')


# IPv6 configuration functions

def start_static_ipv6_network(netcard, inet6, prefixlen):
    """Configure a static IPv6 address on an interface and rebuild the routes.

    Args:
        netcard (str): interface name, for instance em0.
        inet6 (str): IPv6 address.
        prefixlen (str or int): prefix length, for instance 64.
    """
    _run('ifconfig', netcard, 'inet6', inet6, 'prefixlen', str(prefixlen))
    _run('service', 'routing', 'restart')


def enable_slaac(netcard):
    """Turn on stateless address autoconfiguration for an interface.

    accept_rtadv is cleared first so the interface starts from a known
    state, then set, then router advertisements are solicited.

    Args:
        netcard (str): interface name, for instance em0.
    """
    # First disable, then re-enable to ensure clean state
    _run('ifconfig', netcard, 'inet6', '-accept_rtadv')
    sleep(0.5)
    # Enable accept_rtadv for SLAAC
    _run('ifconfig', netcard, 'inet6', 'accept_rtadv')
    # Start rtsold to solicit router advertisements
    _run('rtsol', netcard)


def disable_slaac(netcard):
    """Turn off stateless address autoconfiguration for an interface.

    Args:
        netcard (str): interface name, for instance em0.
    """
    _run('ifconfig', netcard, 'inet6', '-accept_rtadv')


def start_network_card(netcard):
    """Bring one interface up.

    Nothing else is needed. The link coming up fires devd's IFNET LINK_UP
    event, and our action for it, src/link-up.py, starts dhclient, which
    installs the address and the routes.

    Args:
        netcard (str): interface name, for instance em0.
    """
    _run('ifconfig', netcard, 'up')


def disconnect_wifi(wifi_card):
    """Drop the current wireless association and stay disconnected.

    `disconnect` stays disconnected until a network is selected. Downing the
    interface does not: the daemon rejoins as soon as it comes back up.

    Args:
        wifi_card (str): wireless interface name, for instance wlan0.

    Returns:
        bool: True when the daemon accepted the command.
    """
    return wpa_cli(wifi_card, 'disconnect') is not None


def disable_wifi(wifi_card):
    """Take a wireless interface down.

    Args:
        wifi_card (str): wireless interface name, for instance wlan0.
    """
    _run('ifconfig', wifi_card, 'down')


def enable_wifi(wifi_card):
    """Bring a wireless interface up.

    No scan here: the refresh loop requests one on its own clock.

    Args:
        wifi_card (str): wireless interface name, for instance wlan0.
    """
    _run('ifconfig', wifi_card, 'up')


def wpa_cli(wifi_card, *args):
    """
    Ask wpa_supplicant something through its control socket.

    Args:
        wifi_card (str): wireless interface name, which selects the socket.
        *args (str): the wpa_cli command and its arguments, for instance
            'status', or 'set_network', '0', 'ssid', '"name"'.

    Returns:
        str or None: what the daemon answered, or None when it is not
            running, has no control socket, or refused the command with FAIL.
    """
    # -p is where wpa_supplicant exposes its control sockets, one per
    # interface.
    command = ['wpa_cli', '-p', '/var/run/wpa_supplicant',
               '-i', wifi_card] + list(args)
    try:
        out = check_output(
            command,
            stderr=DEVNULL,
            universal_newlines=True,
            timeout=5
        )
    except (CalledProcessError, TimeoutExpired, OSError):
        return None
    if out.startswith('FAIL'):
        return None
    return out


def _printf_decode(text):
    """
    Undo the escaping wpa_supplicant applies to an SSID on its way out.

    The daemon prints every SSID through printf_encode(), so quotes and
    backslashes come back doubled and non-ASCII bytes as \\xHH. Comparing
    that against a plain string silently fails to match.

    Args:
        text (str): one SSID exactly as status, list_networks or
            scan_results printed it.

    Returns:
        str: the real name. Invalid UTF-8 becomes the replacement character
            rather than raising; a beacon can hold anything.
    """
    simple = {'"': 0x22, '\\': 0x5c, 'e': 0x1b, 'n': 0x0a, 'r': 0x0d,
              't': 0x09}
    out = bytearray()
    index = 0
    while index < len(text):
        char = text[index]
        if char != '\\' or index + 1 >= len(text):
            out.extend(char.encode('utf-8'))
            index += 1
            continue
        marker = text[index + 1]
        if marker in simple:
            out.append(simple[marker])
            index += 2
        elif marker == 'x' and index + 3 < len(text):
            out.append(int(text[index + 2:index + 4], 16))
            index += 4
        else:
            out.extend(char.encode('utf-8'))
            index += 1
    return out.decode('utf-8', 'replace')


def _parse_key_values(text):
    """
    Turn wpa_cli's key=value output into a dict.

    Args:
        text (str): output from a command such as status or bss.

    Returns:
        dict: every key=value line, whitespace stripped. Lines without an
            equals sign are ignored, which is what the leading 'Selected
            interface' banner is.
    """
    values = {}
    for line in text.splitlines():
        key, sep, value = line.partition('=')
        if sep:
            values[key.strip()] = value.strip()
    return values


def wpa_status(wifi_card):
    """
    Ask wpa_supplicant what it is currently doing.

    Args:
        wifi_card (str): wireless interface name.

    Returns:
        dict: the fields of `wpa_cli status`, among them wpa_state, ssid,
            bssid, id, key_mgmt and ip_address. Empty when the daemon cannot
            be reached, so callers use .get() rather than testing for None.
    """
    out = wpa_cli(wifi_card, 'status')
    if out is None:
        return {}
    values = _parse_key_values(out)
    if 'ssid' in values:
        values['ssid'] = _printf_decode(values['ssid'])
    return values


def wpa_networks(wifi_card):
    """
    List the saved networks the running daemon knows about.

    Asking the daemon rather than parsing wpa_supplicant.conf means the two
    cannot disagree about which networks exist or how a name was spelled.

    Args:
        wifi_card (str): wireless interface name.

    Returns:
        list[dict]: one dict per saved network with 'id', 'ssid', 'bssid' and
            'flags'. Empty when the daemon cannot be reached.
    """
    out = wpa_cli(wifi_card, 'list_networks')
    if out is None:
        return []
    networks = []
    # network id / ssid / bssid / flags, one network per line after a header
    for line in out.splitlines()[1:]:
        fields = line.split('\t')
        if len(fields) > 3:
            networks.append({
                'id': fields[0].strip(),
                'ssid': _printf_decode(fields[1]),
                'bssid': fields[2],
                'flags': fields[3],
            })
    return networks


def wait_for_daemon(wifi_card, timeout=5):
    """
    Wait for wpa_supplicant's control socket to start answering.

    The socket may not exist yet at boot or after a hot plug. This waits;
    it never restarts anything.

    Args:
        wifi_card (str): wireless interface name.
        timeout (int): seconds to keep trying before giving up.

    Returns:
        bool: True as soon as the daemon answers, False if it never does.
    """
    deadline = monotonic() + timeout
    while True:
        if wpa_cli(wifi_card, 'ping') is not None:
            return True
        if monotonic() >= deadline:
            return False
        sleep(0.25)


def wpa_reconfigure(wifi_card):
    """
    Make wpa_supplicant re-read wpa_supplicant.conf, dropping unsaved edits.

    Run before this attempt's block is written and before a forget is
    saved, so an edit left in the daemon by an abandoned attempt is not
    persisted with them. Network ids are handed out afresh by this, so
    any id read before it is stale. The daemon deauthenticates on it.

    Args:
        wifi_card (str): wireless interface name.

    Returns:
        bool: True when the daemon accepted the command.
    """
    return wpa_cli(wifi_card, 'reconfigure') is not None


def wpa_network_id(wifi_card, ssid):
    """
    Find the daemon's id for a saved network.

    Args:
        wifi_card (str): wireless interface name.
        ssid (str): the network name to look up.

    Returns:
        str or None: the network id, or None when the daemon has no block
            for that name.
    """
    for network in wpa_networks(wifi_card):
        if network['ssid'] == ssid:
            return network['id']
    return None


def enable_all_networks(wifi_card):
    """
    Re-enable every saved network so the card can roam again.

    select_network() disabled the others to pin one; leaving them disabled
    would strand the card, so this must run however the attempt ended.

    Args:
        wifi_card (str): wireless interface name.

    Returns:
        bool: True when the daemon accepted the command.
    """
    return wpa_cli(wifi_card, 'enable_network', 'all') is not None


def connect_to_ssid(ssid, wifi_card):
    """
    Join one saved network, and only that one.

    select_network disables every other saved network, so the caller must
    call enable_all_networks() once the attempt has finished either way.

    Args:
        ssid (str): the network name to join. The daemon must already hold
            a block for it, saved to the file or not.
        wifi_card (str): wireless interface name.

    Returns:
        bool: True when the daemon accepted the selection, which is the
            start of the attempt and not its outcome. Follow it with
            wait_for_connection().
    """
    if not wait_for_daemon(wifi_card):
        return False
    network_id = wpa_network_id(wifi_card, ssid)
    if network_id is None:
        return False
    return wpa_cli(wifi_card, 'select_network', network_id) is not None


def _printf_encode(value):
    """
    Escape a value the way wpa_supplicant's own printf_encode() does.

    The exact inverse of _printf_decode, so a name read back out of the
    daemon can be handed straight back to it.

    Args:
        value (str): the raw text.

    Returns:
        str: printable ASCII, with quotes, backslashes and control
            characters escaped and every other byte written as \\xHH.
    """
    simple = {0x22: '\\"', 0x5c: '\\\\', 0x1b: '\\e', 0x0a: '\\n',
              0x0d: '\\r', 0x09: '\\t'}
    out = []
    for byte in value.encode('utf-8'):
        if byte in simple:
            out.append(simple[byte])
        elif 32 <= byte <= 126:
            out.append(chr(byte))
        else:
            out.append(f'\\x{byte:02x}')
    return ''.join(out)


def _quoted(value):
    """
    Render a value for set_network using wpa_supplicant's escaped form.

    A plain "..." is taken literally, so hand-added backslashes are stored
    as backslashes. P"..." is the form that gets decoded, and keeps the
    command printable ASCII whatever the beacon held.

    Args:
        value (str): the raw value, such as an SSID or an identity.

    Returns:
        str: the value wrapped as P"..." and ready for set_network.
    """
    return f'P"{_printf_encode(value)}"'


def _plain_quoted(value):
    """
    Render a value for the fields that only accept plain quotes.

    wpa_config_parse_psk() takes a quoted passphrase or a hex key and
    nothing else, so psk cannot use P"...". Nothing is escaped: the parser
    reads first quote to last, so an embedded quote survives.

    Args:
        value (str): the raw passphrase.

    Returns:
        str: the passphrase wrapped in double quotes.
    """
    return f'"{value}"'


def wpa_save_config(wifi_card):
    """
    Ask the daemon to write wpa_supplicant.conf, then lock the file down.

    The daemon's own chmod of the temporary file is #ifdef ANDROID, so on
    FreeBSD the rename leaves whatever its umask produced. The file holds
    passphrases, so 0600 has to be put back every time.

    Args:
        wifi_card (str): wireless interface name.

    Returns:
        bool: True when the daemon reported the file written.
    """
    if wpa_cli(wifi_card, 'save_config') is None:
        return False
    os.chmod('/etc/wpa_supplicant.conf', 0o600)
    return True


def _save_network(wifi_card, fields):
    """
    Create one saved network from a list of fields, in the daemon only.

    Nothing reaches wpa_supplicant.conf here. The caller runs
    wpa_save_config() once the network has actually connected, so a
    passphrase that turns out to be wrong is never written to disk.

    add_network creates the network disabled, so it is enabled here rather
    than at save time; the config writer records the disabled flag and would
    leave a network that never joins after a restart.

    Args:
        wifi_card (str): wireless interface name.
        fields (list[tuple[str, str]]): (name, value) pairs to set, with
            values already quoted where wpa_supplicant expects a string.

    Returns:
        str or None: the new network's id, or None when anything failed. A
            half-built network is removed rather than left behind.
    """
    if not wait_for_daemon(wifi_card):
        return None
    answer = wpa_cli(wifi_card, 'add_network')
    if answer is None:
        return None
    network_id = answer.strip().splitlines()[-1].strip()
    for name, value in fields:
        if wpa_cli(wifi_card, 'set_network', network_id, name, value) is None:
            wpa_cli(wifi_card, 'remove_network', network_id)
            return None
    if wpa_cli(wifi_card, 'enable_network', network_id) is None:
        wpa_cli(wifi_card, 'remove_network', network_id)
        return None
    return network_id


def _wep_key_value(key):
    """
    Render a WEP key as either a hex value or a quoted ASCII one.

    wpa_supplicant reads a bare wep_key0 as hex and a quoted one as ASCII,
    and requires 5, 13 or 16 bytes either way. So only 10, 26 or 32 hex
    digits can be meant as hex; everything else is ASCII and must be quoted.

    Args:
        key (str): the key exactly as the user typed it.

    Returns:
        str: the key ready for set_network, bare when it is hex and quoted
            when it is ASCII.
    """
    if len(key) in (10, 26, 32) and all(c in hexdigits for c in key):
        return key
    return _quoted(key)


def save_psk_network(ssid, security, pwd, wifi_card):
    """
    Save a PSK or WEP network through the daemon.

    Args:
        ssid (str): the network name.
        security (str): the security type from security_from_flags, one of
            WPA2-PSK, WPA-PSK, WPA3-SAE or WEP.
        pwd (str): the passphrase, or the key for a WEP network.
        wifi_card (str): wireless interface name.

    Returns:
        str or None: the new network's id, or None when the save failed.

    Raises:
        ValueError: for a security type this writer does not cover, such as
            enterprise or open, which have their own savers.
    """
    # A WPA2/WPA3 transition network reports SAE alongside PSK and joins
    # perfectly well with a passphrase, so it is saved as RSN here.
    if security in ('WPA2-PSK', 'WPA3-SAE'):
        fields = [
            ('ssid', _quoted(ssid)),
            ('key_mgmt', 'WPA-PSK'),
            ('proto', 'RSN'),
            ('psk', _plain_quoted(pwd)),
        ]
    elif security == 'WPA-PSK':
        fields = [
            ('ssid', _quoted(ssid)),
            ('key_mgmt', 'WPA-PSK'),
            ('proto', 'WPA'),
            ('psk', _plain_quoted(pwd)),
        ]
    elif security == 'WEP':
        fields = [
            ('ssid', _quoted(ssid)),
            ('key_mgmt', 'NONE'),
            ('wep_tx_keyidx', '0'),
            ('wep_key0', _wep_key_value(pwd)),
        ]
    else:
        raise ValueError(f'{security} is not a PSK or WEP network')
    return _save_network(wifi_card, fields)


def update_psk_network(ssid, pwd, wifi_card):
    """
    Change the passphrase on a network that is already saved.

    Only the psk field is wrong, so it is replaced in place; deleting and
    re-adding would discard everything else on the block.

    The change is made in the daemon only. The file keeps the old passphrase
    until the new one has connected and the caller runs wpa_save_config(),
    so retyping a password badly cannot destroy one that worked.

    Args:
        ssid (str): the network name, which must already be saved.
        pwd (str): the new passphrase.
        wifi_card (str): wireless interface name.

    Returns:
        bool: True when the daemon took the new passphrase.
    """
    if not wait_for_daemon(wifi_card):
        return False
    network_id = wpa_network_id(wifi_card, ssid)
    if network_id is None:
        return False
    if wpa_cli(wifi_card, 'set_network', network_id, 'psk',
               _plain_quoted(pwd)) is None:
        return False
    return wpa_cli(wifi_card, 'enable_network', network_id) is not None


def save_open_network(ssid, wifi_card):
    """
    Save an open network through the daemon.

    Args:
        ssid (str): the network name.
        wifi_card (str): wireless interface name.

    Returns:
        str or None: the new network's id, or None when the save failed.
    """
    return _save_network(wifi_card, [
        ('ssid', _quoted(ssid)),
        ('key_mgmt', 'NONE'),
    ])


def _phase2_value(eap_method, phase2):
    """
    Build the phase2 string for an inner authentication method.

    PEAP always takes `auth=`. TTLS accepts only MSCHAPV2, MSCHAP, PAP and
    CHAP after `auth=` (eap_ttls.c refuses to start otherwise), so EAP inner
    methods must go through `autheap=`.

    Args:
        eap_method (str): the outer method, such as PEAP or TTLS.
        phase2 (str): the inner method, one of PHASE2_METHODS.

    Returns:
        str: the phase2 field value, for instance "auth=MSCHAPV2" or
            "autheap=GTC".
    """
    if eap_method == 'TTLS' and phase2 not in ('MSCHAPV2', 'MSCHAP', 'PAP', 'CHAP'):
        return f'autheap={phase2}'
    return f'auth={phase2}'


def save_eap_network(ssid, eap_config, wifi_card):
    """
    Save an enterprise (802.1X/EAP) network through the daemon.

    Args:
        ssid (str): the network name.
        eap_config (dict): the credentials collected by the EAP dialog, with
            eap_method, identity, password, phase2, anonymous_identity,
            ca_cert, client_cert, private_key, private_key_passwd and
            domain_suffix_match. Only eap_method and identity are required.
        wifi_card (str): wireless interface name.

    Returns:
        str or None: the new network's id, or None when the save failed.
    """
    eap_method = eap_config.get('eap_method', 'PEAP')
    fields = [
        ('ssid', _quoted(ssid)),
        ('key_mgmt', 'WPA-EAP'),
        ('eap', eap_method),
        ('identity', _quoted(eap_config.get('identity', ''))),
    ]
    anonymous_identity = eap_config.get('anonymous_identity', '')
    if anonymous_identity:
        fields.append(('anonymous_identity', _quoted(anonymous_identity)))
    if eap_method == 'TLS':
        # TLS authenticates with a client certificate rather than a password.
        for name in ('client_cert', 'private_key', 'private_key_passwd'):
            value = eap_config.get(name, '')
            if value:
                fields.append((name, _quoted(value)))
    else:
        fields.append(('password', _quoted(eap_config.get('password', ''))))
        phase2 = eap_config.get('phase2', 'MSCHAPV2')
        if phase2:
            fields.append(
                ('phase2', _quoted(_phase2_value(eap_method, phase2)))
            )
    for name in ('ca_cert', 'domain_suffix_match'):
        value = eap_config.get(name, '')
        if value:
            fields.append((name, _quoted(value)))
    if not wait_for_daemon(wifi_card):
        return None
    # Retyping credentials replaces the block rather than adding a second
    # one, because wpa_network_id returns the lowest id and the retry would
    # otherwise keep selecting the credentials that just failed.
    _remove_networks(wifi_card, ssid)
    return _save_network(wifi_card, fields)


def _remove_networks(wifi_card, ssid):
    """
    Drop every saved network with this name from the daemon.

    Nothing is written to disk, so the caller decides whether this is a
    removal or is making room for a replacement block.

    Args:
        wifi_card (str): wireless interface name.
        ssid (str): the network name to remove.

    Returns:
        bool: True when at least one network was removed.
    """
    removed = False
    # Ids shift as networks are removed, so the list is re-read each time.
    while True:
        network_id = wpa_network_id(wifi_card, ssid)
        if network_id is None:
            break
        if wpa_cli(wifi_card, 'remove_network', network_id) is None:
            break
        removed = True
    return removed


def forget_network(ssid, wifi_card):
    """
    Remove every saved network with this name and persist the removal.

    Args:
        ssid (str): the network name to forget.
        wifi_card (str): wireless interface name.

    Returns:
        bool: True when at least one network was removed and written out.
    """
    if not wait_for_daemon(wifi_card):
        return False
    if not _remove_networks(wifi_card, ssid):
        return False
    return wpa_save_config(wifi_card)


def ssid_is_saved(ssid, wifi_card):
    """
    Report whether the daemon already holds a network block for a name.

    Asking the daemon rather than reading wpa_supplicant.conf means the two
    cannot disagree about which networks exist or how a name was spelled.

    Args:
        ssid (str): the network name to look for.
        wifi_card (str): wireless interface name.

    Returns:
        bool: True when a saved network carries that name.
    """
    return wpa_network_id(wifi_card, ssid) is not None


def security_from_flags(flags):
    """
    Read the security type out of a scan result's flags.

    PSK is tested before SAE on purpose: a WPA2/WPA3 transition AP
    advertises both as [WPA2-PSK+SAE-CCMP] and joins with a passphrase,
    while SAE needs a wpa_supplicant built with it.

    Args:
        flags (str): the flags column, for instance '[WPA2-PSK-CCMP][ESS]'.

    Returns:
        str: one of WPA2-EAP, WPA-EAP, WPA2-PSK, WPA-PSK, WPA3-SAE, WEP or
            OPEN.
    """
    modern = 'WPA2' in flags or 'RSN' in flags
    if 'EAP' in flags:
        return 'WPA2-EAP' if modern else 'WPA-EAP'
    if 'PSK' in flags:
        return 'WPA2-PSK' if modern else 'WPA-PSK'
    if 'SAE' in flags:
        return 'WPA3-SAE'
    if 'WEP' in flags:
        return 'WEP'
    return 'OPEN'


# Noise readings already taken, keyed by interface. See _noise_floor.
_NOISE_FLOOR = {}


def _noise_floor(wifi_card):
    """
    Return the radio's noise floor, which the scan results do not carry.

    Cached per interface: noise belongs to the radio, not the access point,
    and does not move. A failed reading is deliberately not cached, since
    the BSS table is empty until the first scan completes.

    Args:
        wifi_card (str): wireless interface name.

    Returns:
        int: noise in dBm from the daemon's BSS table, or -95 when the
            driver does not report it.
    """
    if wifi_card in _NOISE_FLOOR:
        return _NOISE_FLOOR[wifi_card]
    out = wpa_cli(wifi_card, 'bss', '0')
    if out:
        noise = _parse_key_values(out).get('noise')
        if noise:
            _NOISE_FLOOR[wifi_card] = int(noise)
            return _NOISE_FLOOR[wifi_card]
    return -95


def request_scan(wifi_card):
    """
    Ask the daemon to scan for access points now.

    Unlike `ifconfig scan` this works as an unprivileged user. It is also the
    only way to force a refresh: reading scan results never triggers one.

    Args:
        wifi_card (str): wireless interface name.

    Returns:
        bool: True when the daemon accepted the request.
    """
    return wpa_cli(wifi_card, 'scan') is not None


def request_scan_all():
    """Ask every wireless card to scan.

    Called on the refresh tick and when the menu opens, so the BSS table is
    already warm by the time a submenu is drawn from it.
    """
    for card in nics_list():
        if 'wlan' in card:
            request_scan(card)


def scan_networks(wifi_card):
    """
    List the access points in range.

    Reads the BSS table only. It expires entries after bss_expiration_age
    (180s) and autoscan refills it only while disconnected, so something
    has to call request_scan_all() for this to stay current.

    Args:
        wifi_card (str): wireless interface name.

    Returns:
        dict: maps each SSID to a record with 'ssid', 'bssid', 'frequency',
            'level', 'noise', 'signal', 'flags', 'security' and 'enterprise'.
            Strongest access point wins; hidden networks are left out.
    """
    out = wpa_cli(wifi_card, 'scan_results')
    if out is None:
        return {}
    noise = _noise_floor(wifi_card)
    networks = {}
    # bssid / frequency / signal level / flags / ssid, after a header line
    for line in out.splitlines()[1:]:
        fields = line.split('\t')
        if len(fields) < 5:
            continue
        ssid = _printf_decode(fields[4])
        if not ssid:
            continue
        level = int(fields[2])
        signal = bar_percent(level, noise)
        if ssid in networks and networks[ssid]['signal'] >= signal:
            continue
        flags = fields[3]
        security = security_from_flags(flags)
        networks[ssid] = {
            'ssid': ssid,
            'bssid': fields[0],
            'frequency': int(fields[1]),
            'level': level,
            'noise': noise,
            'signal': signal,
            'flags': flags,
            'security': security,
            'enterprise': security.endswith('-EAP'),
        }
    return networks


def wait_for_connection(wifi_card, ssid, timeout=30):
    """
    Watch a connection attempt and report whether it joined.

    COMPLETED alone is not success: the daemon still reports the previous
    association for a moment after select_network, so the reported ssid has
    to match the one asked for.

    A refused key cannot be told from a card that never answered. That would
    need wpas_auth_failed() to fire, and on driver_bsd it does not: tested
    2026-09-10 with a knowingly wrong passphrase, every attempt ran the full
    timeout without the network ever being marked TEMP-DISABLED.

    Args:
        wifi_card (str): wireless interface name.
        ssid (str): the network the caller asked to join.
        timeout (int): seconds to wait before giving up.

    Returns:
        bool: True once the card is joined to ssid, False on timeout.
    """
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        status = wpa_status(wifi_card)
        if status.get('wpa_state') == 'COMPLETED' and status.get('ssid') == ssid:
            return True
        sleep(0.5)
    return False


def subnet_hex_to_dec(ifconfig_string):
    """
    Rewrite the hexadecimal netmask in an ifconfig line as dotted decimal.

    ifconfig prints `netmask 0xffffff00`, which no one reads at a glance.

    Args:
        ifconfig_string (str): an ifconfig line, normally the `inet ` one.

    Returns:
        str: the same line with the mask as 255.255.255.0. The line is
            returned untouched when it holds no hexadecimal mask, which is
            the case for an interface with no IPv4 address.
    """
    found = re.search('0x.{8}', ifconfig_string)
    if found is None:
        return ifconfig_string
    snethexlist = re.findall('..', found.group(0)[2:])
    snetdec = ".".join(str(int(li, 16)) for li in snethexlist)
    return ifconfig_string.replace(found.group(0), snetdec)


def wait_for_address(card, timeout=5):
    """Wait for an interface to hold an IPv4 address.

    Best effort: the caller renews the lease afterwards either way, so a
    timeout here means a slow interface, not a failure.

    Nothing waits on ifconfig's status word. An interface cannot hold a
    leased IPv4 address with the link down, so the address is the only
    thing worth watching, and waiting for "active" was the half that could
    never finish on an unplugged card.

    Args:
        card (str): interface name, for instance em0 or wlan0.
        timeout (int): seconds to wait before giving up.
    """
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        ifoutput = _run('ifconfig', '-f', 'inet:dotted', card).stdout
        if re.search(fr'inet {IP_REGEX}', ifoutput):
            return
        sleep(0.1)
