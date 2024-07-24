#!/usr/bin/env python

from subprocess import Popen, PIPE, run, check_output
import re
from time import sleep


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
    # with spaces in them. These ssid strings will be double quoted by ifconfig
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
                info.append(line[83:].strip())
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
    wpa_supplicant_conf = open('/etc/wpa_supplicant.conf', 'w')
    wpa_supplicant_conf.writelines(left_over)
    wpa_supplicant_conf.close()


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
