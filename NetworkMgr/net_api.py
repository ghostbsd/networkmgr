#!/usr/bin/env python

from subprocess import Popen, PIPE, run, check_output
import os
import re
from time import sleep


# EAP methods supported for enterprise WPA
EAP_METHODS = ['PEAP', 'TTLS', 'TLS', 'LEAP', 'FAST', 'PWD']

# Phase 2 (inner) authentication methods
PHASE2_METHODS = ['MSCHAPV2', 'GTC', 'PAP', 'CHAP', 'MD5']

# Default CA certificate path on FreeBSD/GhostBSD
DEFAULT_CA_CERT = '/etc/ssl/certs/ca-root-nss.crt'


def card_online(netcard):
    lan = Popen('ifconfig ' + netcard, shell=True, stdout=PIPE,
                universal_newlines=True)
    return 'inet ' in lan.stdout.read()


def defaultcard():
    cmd = "netstat -rn | grep default"
    nics = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    device = nics.stdout.readlines()
    if len(device) == 0:
        return None
    else:
        return list(filter(None, device[0].rstrip().split()))[3]


def ifWlanDisable(wificard):
    cmd = "ifconfig %s list scan" % wificard
    nics = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    return not nics.stdout.read()


def ifStatue(wificard):
    cmd = "ifconfig %s" % wificard
    wl = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    wlout = wl.stdout.read()
    return "associated" in wlout


def get_ssid(wificard):
    wlan = Popen('ifconfig %s | grep ssid' % wificard,
                 shell=True, stdout=PIPE, universal_newlines=True)
    # If there are quotation marks in the string, use that as a separator,
    # otherwise use the default whitespace. This is to handle ssid strings
    # with spaces in them. These ssid strings will be double-quoted by ifconfig
    temp = wlan.stdout.readlines()[0].rstrip()
    if '"' in temp:
        out = temp.split('"')[1]
    else:
        out = temp.split()[1]
    return out


def nics_list():
    not_nics_regex = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|" \
        r"faith|ppp|bridge|wg)[0-9]+(\s*)|vm-[a-z]+(\s*)"
    nics = Popen(
        'ifconfig -l',
        shell=True,
        stdout=PIPE,
        universal_newlines=True
    ).stdout.read().strip()
    return sorted(re.sub(not_nics_regex, '', nics).strip().split())


def ifcardconnected(netcard):
    wifi = Popen('ifconfig ' + netcard, shell=True, stdout=PIPE,
                 universal_newlines=True)
    return 'status: active' in wifi.stdout.read()


def barpercent(sn):
    sig = int(sn.partition(':')[0])
    noise = int(sn.partition(':')[2])
    return int((sig - noise) * 4)


def is_enterprise_network(caps_string):
    """
    Detect if a network uses WPA-Enterprise (802.1X/EAP) authentication.

    FreeBSD ifconfig scan doesn't explicitly distinguish PSK from EAP.
    We use heuristics based on capability flags:

    1. Explicit EAP indicators (if present)
    2. RSN without WPS AND without typical home router flags (HTCAP, VHTCAP, ATH)
       suggests a minimal enterprise AP configuration

    Note: This is imperfect - some networks may be misdetected.
    """
    caps_upper = caps_string.upper()

    # Explicit enterprise indicators (highest confidence)
    enterprise_indicators = ['EAP', '802.1X', 'WPA2-EAP', 'WPA-EAP', 'RSN-EAP']
    for indicator in enterprise_indicators:
        if indicator in caps_upper:
            return True

    # Heuristic: RSN without WPS and without typical consumer router features
    # Enterprise APs often have minimal beacon flags
    has_rsn = 'RSN' in caps_upper
    has_wps = 'WPS' in caps_upper
    has_consumer_features = any(f in caps_upper for f in ['HTCAP', 'VHTCAP', 'ATH', 'WME'])

    # Only flag as enterprise if: has RSN, no WPS, and no typical consumer features
    if has_rsn and not has_wps and not has_consumer_features:
        return True

    return False


def get_security_type(caps_string):
    """
    Determine the security type of a wireless network.
    Returns: 'OPEN', 'WEP', 'WPA-PSK', 'WPA2-PSK', 'WPA-EAP', 'WPA2-EAP'
    """
    caps_upper = caps_string.upper()
    if is_enterprise_network(caps_string):
        if 'RSN' in caps_upper or 'WPA2' in caps_upper:
            return 'WPA2-EAP'
        return 'WPA-EAP'
    elif 'RSN' in caps_upper:
        return 'WPA2-PSK'
    elif 'WPA' in caps_upper:
        return 'WPA-PSK'
    elif 'WEP' in caps_upper or 'PRIVACY' in caps_upper:
        return 'WEP'
    return 'OPEN'


def validate_certificate(cert_path):
    """
    Validate that a certificate file exists and is readable.
    Returns tuple (is_valid, error_message).
    """
    if not cert_path:
        return False, "No certificate path provided"
    if not os.path.exists(cert_path):
        return False, f"Certificate file not found: {cert_path}"
    if not os.path.isfile(cert_path):
        return False, f"Not a file: {cert_path}"
    if not os.access(cert_path, os.R_OK):
        return False, f"Certificate file not readable: {cert_path}"
    return True, None


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


def network_service_state():
    return False


def networkdictionary():
    nlist = nics_list()
    maindictionary = {
        'service': network_service_state(),
        'default': defaultcard()
    }
    cards = {}
    for card in nlist:
        if 'wlan' in card:
            scanv = f"ifconfig {card} list scan | grep -va BSSID"
            wifi = Popen(scanv, shell=True, stdout=PIPE,
                         universal_newlines=True)
            connectioninfo = {}
            for line in wifi.stdout:
                # don't sort empty ssid
                # Window, MacOS and Linux does not show does
                if line.startswith(" " * 5):
                    continue
                ssid = line[:33].strip()
                info = line[:83][33:].strip().split()
                percentage = barpercent(info[3])
                # if ssid exist and percentage is higher keep it
                # else add the new one if percentage is higher
                if ssid in connectioninfo:
                    if connectioninfo[ssid][4] > percentage:
                        continue
                info[3] = percentage
                info.insert(0, ssid)
                # append left over
                caps_string = line[83:].strip()
                info.append(caps_string)
                # Add security type info (index 7)
                info.append(get_security_type(caps_string))
                # Add enterprise flag (index 8)
                info.append(is_enterprise_network(caps_string))
                connectioninfo[ssid] = info
            if ifWlanDisable(card):
                connectionstat = {
                    "connection": "Disabled",
                    "ssid": None,
                }
            elif not ifStatue(card):
                connectionstat = {
                    "connection": "Disconnected",
                    "ssid": None,
                }
            else:
                ssid = get_ssid(card)
                connectionstat = {
                    "connection": "Connected",
                    "ssid": ssid,
                }
            seconddictionary = {
                'state': connectionstat,
                'info': connectioninfo
            }
        else:
            if card_online(card):
                connectionstat = {"connection": "Connected"}
            elif ifcardconnected(card):
                connectionstat = {"connection": "Disconnected"}
            else:
                connectionstat = {"connection": "Unplug"}
            seconddictionary = {'state': connectionstat, 'info': None}
        cards[card] = seconddictionary
    maindictionary['cards'] = cards
    return maindictionary


def connectionStatus(card: str, network_info: dict) -> str:
    if card is None:
        netstate = "Network card is not enabled"
    elif 'wlan' in card:
        if not ifWlanDisable(card) and ifStatue(card):
            cmd1 = "ifconfig %s | grep ssid" % card
            cmd2 = "ifconfig %s | grep 'inet '" % card
            out1 = Popen(cmd1, shell=True, stdout=PIPE, universal_newlines=True)
            out2 = Popen(cmd2, shell=True, stdout=PIPE, universal_newlines=True)
            ssid_info = out1.stdout.read().strip()
            inet_info = out2.stdout.read().strip()
            ssid = network_info['cards'][card]['state']["ssid"]
            percentage = network_info['cards'][card]['info'][ssid][4]
            netstate = f"Signal Strength: {percentage}% \n{ssid_info} \n{subnetHexToDec(inet_info)}"
        else:
            netstate = "WiFi %s not connected" % card
    else:
        cmd = "ifconfig %s | grep 'inet '" % card
        out = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
        line = out.stdout.read().strip()
        netstate = subnetHexToDec(line)
    return netstate


def switch_default(nic):
    nics = nics_list()
    nics.remove(nic)
    if not nics:
        return
    for card in nics:
        nic_info = Popen(
            ['ifconfig', card],
            stdout=PIPE,
            close_fds=True,
            universal_newlines=True
        ).stdout.read()
        if 'status: active' in nic_info or 'status: associated' in nic_info:
            if 'inet ' in nic_info or 'inet6' in nic_info:
                run(f'service dhclient restart {card}', shell=True)
                break
    return


def restart_all_nics(widget):
    run('service netif restart', shell=True)


def stopallnetwork():
    run('service netif stop', shell=True)


def startallnetwork():
    run('service netif start', shell=True)


def stopnetworkcard(netcard):
    run(f'service netif stop {netcard}', shell=True)
    switch_default(netcard)


def restart_card_network(netcard):
    run(f'service netif restart {netcard}', shell=True)


def restart_routing_and_dhcp(netcard):
    run('service routing restart', shell=True)
    sleep(1)
    run(f'service dhclient restart {netcard}', shell=True)


def start_static_network(netcard, inet, netmask):
    run(f'ifconfig {netcard} inet {inet} netmask {netmask}', shell=True)
    sleep(1)
    run('service routing restart', shell=True)


# IPv6 configuration functions

def start_static_ipv6_network(netcard, inet6, prefixlen):
    """Configure a static IPv6 address on the given interface."""
    run(f'ifconfig {netcard} inet6 {inet6} prefixlen {prefixlen}', shell=True)
    sleep(1)
    run('service routing restart', shell=True)


def enable_slaac(netcard):
    """Enable SLAAC (Stateless Address Autoconfiguration) on the interface."""
    # Remove any existing IPv6 addresses first
    run(f'ifconfig {netcard} inet6 -accept_rtadv', shell=True)
    sleep(0.5)
    # Enable accept_rtadv for SLAAC
    run(f'ifconfig {netcard} inet6 accept_rtadv', shell=True)
    # Start rtsold to solicit router advertisements
    run(f'rtsol {netcard}', shell=True)


def disable_slaac(netcard):
    """Disable SLAAC on the interface."""
    run(f'ifconfig {netcard} inet6 -accept_rtadv', shell=True)


def get_ipv6_addresses(netcard):
    """Get all IPv6 addresses configured on the interface."""
    try:
        output = check_output(f'ifconfig {netcard}', shell=True, universal_newlines=True)
        # Match inet6 addresses, excluding link-local (fe80::) and localhost (::1)
        addresses = re.findall(r'inet6 ([0-9a-fA-F:]+)%?\S* prefixlen (\d+)', output)
        return [(addr, int(prefixlen)) for addr, prefixlen in addresses]
    except Exception:
        return []


def has_slaac_enabled(netcard):
    """Check if SLAAC (accept_rtadv) is enabled on the interface."""
    try:
        output = check_output(f'ifconfig {netcard}', shell=True, universal_newlines=True)
        return 'ACCEPT_RTADV' in output
    except Exception:
        return False


def get_ipv6_gateway():
    """Get the default IPv6 gateway from routing table."""
    try:
        output = check_output('netstat -rn -f inet6', shell=True, universal_newlines=True)
        for line in output.splitlines():
            if line.startswith('default'):
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1]
    except Exception:
        pass
    return ""


def startnetworkcard(netcard):
    run(f'service netif start {netcard}', shell=True)
    sleep(1)
    run('service routing restart', shell=True)
    run(f'service dhclient start {netcard}', shell=True)


def wifiDisconnection(wificard):
    run(f'ifconfig {wificard} down', shell=True)
    run(f"ifconfig {wificard} ssid 'none'", shell=True)
    run(f'ifconfig {wificard} up', shell=True)


def disableWifi(wificard):
    run(f'ifconfig {wificard} down', shell=True)


def enableWifi(wificard):
    run(f'ifconfig {wificard} up', shell=True)
    run(f'ifconfig {wificard} up scan', shell=True)


def connectToSsid(name, wificard):
    run('killall wpa_supplicant', shell=True)
    # service
    sleep(0.5)
    run(f"ifconfig {wificard} ssid '{name}'", shell=True)
    sleep(0.5)
    wpa_supplicant = run(
        f'wpa_supplicant -B -i {wificard} -c /etc/wpa_supplicant.conf',
        shell=True
    )
    return wpa_supplicant.returncode == 0


def subnetHexToDec(ifconfigstring):
    snethex = re.search('0x.{8}', ifconfigstring).group(0)[2:]
    snethexlist = re.findall('..', snethex)
    snetdec = ".".join(str(int(li, 16)) for li in snethexlist)
    outputline = ifconfigstring.replace(re.search('0x.{8}', ifconfigstring).group(0), snetdec)
    return outputline


def get_ssid_wpa_supplicant_config(ssid):
    cmd = f"""grep -A 3 'ssid="{ssid}"' /etc/wpa_supplicant.conf"""
    out = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    return out.stdout.read().splitlines()


def delete_ssid_wpa_supplicant_config(ssid):
    cmd = f"""awk '/sid="{ssid}"/ """ \
        """{print NR-2 "," NR+4 "d"}' """ \
        """/etc/wpa_supplicant.conf | sed -f - /etc/wpa_supplicant.conf"""
    out = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    left_over = out.stdout.read()
    old_umask = os.umask(0o077)
    try:
        with open('/etc/wpa_supplicant.conf', 'w') as wpa_supplicant_conf:
            wpa_supplicant_conf.write(left_over)
        os.chmod('/etc/wpa_supplicant.conf', 0o600)
    finally:
        os.umask(old_umask)


def nic_status(card):
    out = Popen(
        f'ifconfig {card} | grep status:',
        shell=True, stdout=PIPE,
        universal_newlines=True
    )
    return out.stdout.read().split(':')[1].strip()


def start_dhcp(wificard):
    run(f'dhclient {wificard}', shell=True)


def wait_inet(card):
    IPREGEX = r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+'
    status = 'associated' if 'wlan' in card else 'active'
    while nic_status(card) != status:
        sleep(0.1)
        print(nic_status(card))
    while True:
        ifcmd = f"ifconfig -f inet:dotted {card}"
        ifoutput = check_output(ifcmd.split(" "), universal_newlines=True)
        print(ifoutput)
        re_ip = re.search(fr'inet {IPREGEX}', ifoutput)
        if re_ip and '0.0.0.0' not in re_ip.group():
            print(re_ip)
            break


def _escape_wpa_value(value):
    """Escape special characters for wpa_supplicant.conf quoted strings."""
    if not value:
        return value
    # Escape backslashes first, then quotes
    return value.replace('\\', '\\\\').replace('"', '\\"')


def generate_eap_config(ssid, eap_config):
    """
    Generate wpa_supplicant network block for EAP/Enterprise authentication.

    eap_config dict should contain:
        - eap_method: 'PEAP', 'TTLS', 'TLS', etc.
        - identity: username
        - password: password (for PEAP/TTLS)
        - ca_cert: path to CA certificate (optional)
        - client_cert: path to client certificate (for TLS)
        - private_key: path to private key (for TLS)
        - private_key_passwd: private key password (for TLS)
        - phase2: inner authentication method (for PEAP/TTLS)
        - anonymous_identity: anonymous outer identity (optional)
        - domain_suffix_match: server domain validation (optional)
    """
    eap_method = eap_config.get('eap_method', 'PEAP')
    identity = _escape_wpa_value(eap_config.get('identity', ''))
    password = _escape_wpa_value(eap_config.get('password', ''))
    ca_cert = _escape_wpa_value(eap_config.get('ca_cert', ''))
    client_cert = _escape_wpa_value(eap_config.get('client_cert', ''))
    private_key = _escape_wpa_value(eap_config.get('private_key', ''))
    private_key_passwd = _escape_wpa_value(eap_config.get('private_key_passwd', ''))
    phase2 = eap_config.get('phase2', 'MSCHAPV2')
    anonymous_identity = _escape_wpa_value(eap_config.get('anonymous_identity', ''))
    domain_suffix_match = _escape_wpa_value(eap_config.get('domain_suffix_match', ''))
    ssid_escaped = _escape_wpa_value(ssid)

    ws = '\nnetwork={'
    ws += f'\n\tssid="{ssid_escaped}"'
    ws += '\n\tkey_mgmt=WPA-EAP'
    ws += f'\n\teap={eap_method}'
    ws += f'\n\tidentity="{identity}"'

    if anonymous_identity:
        ws += f'\n\tanonymous_identity="{anonymous_identity}"'

    if eap_method == 'TLS':
        # TLS requires client certificate
        if client_cert:
            ws += f'\n\tclient_cert="{client_cert}"'
        if private_key:
            ws += f'\n\tprivate_key="{private_key}"'
        if private_key_passwd:
            ws += f'\n\tprivate_key_passwd="{private_key_passwd}"'
    else:
        # PEAP, TTLS, etc. use password
        ws += f'\n\tpassword="{password}"'
        if phase2:
            if eap_method == 'TTLS':
                ws += f'\n\tphase2="auth={phase2}"'
            else:  # PEAP
                ws += f'\n\tphase2="auth={phase2}"'

    if ca_cert:
        ws += f'\n\tca_cert="{ca_cert}"'

    if domain_suffix_match:
        ws += f'\n\tdomain_suffix_match="{domain_suffix_match}"'

    ws += '\n}\n'
    return ws


def write_eap_config(ssid, eap_config):
    """
    Write EAP configuration to wpa_supplicant.conf with secure permissions.
    """
    config = generate_eap_config(ssid, eap_config)
    wpa_conf_path = '/etc/wpa_supplicant.conf'

    # Write with restrictive permissions (owner read/write only)
    old_umask = os.umask(0o077)
    try:
        with open(wpa_conf_path, 'a') as wsf:
            wsf.write(config)
    finally:
        os.umask(old_umask)

    # Ensure file permissions are correct
    try:
        os.chmod(wpa_conf_path, 0o600)
    except PermissionError:
        pass  # May need root, handled by sudoers
