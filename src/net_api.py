#!/usr/bin/env python3

from subprocess import Popen, PIPE, run
from sys import path
import os
import re
from time import sleep
path.append("/usr/local/share/networkmgr")


def card_online(netcard):
    lan = Popen('ifconfig ' + netcard, shell=True, stdout=PIPE,
                universal_newlines=True)
    if 'inet ' in lan.stdout.read():
        return True
    else:
        return False


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
    if "" == nics.stdout.read():
        return True
    else:
        return False


def ifStatue(wificard):
    cmd = "ifconfig %s" % wificard
    wl = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    wlout = wl.stdout.read()
    if "associated" in wlout:
        return True
    else:
        return False


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
    notnics_regex = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|" \
        r"faith|ppp|bridge|wg)[0-9]+(\s*)|vm-[a-z]+(\s*)"
    nics = Popen(
        'ifconfig -l',
        shell=True,
        stdout=PIPE,
        universal_newlines=True
    ).stdout.read().strip()
    return sorted(re.sub(notnics_regex, '', nics).strip().split())


def ifcardconnected(netcard):
    wifi = Popen('ifconfig ' + netcard, shell=True, stdout=PIPE,
                 universal_newlines=True)
    if 'status: active' in wifi.stdout.read():
        return True
    else:
        return False


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
                if line[:5] == "     ":
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
            if ifWlanDisable(card) is True:
                connectionstat = {
                    "connection": "Disabled",
                    "ssid": None,
                }
            elif ifStatue(card) is False:
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
            if card_online(card) is True:
                connectionstat = {"connection": "Connected"}
            elif ifcardconnected(card) is True:
                connectionstat = {"connection": "Disconnected"}
            else:
                connectionstat = {"connection": "Unplug"}
            seconddictionary = {'state': connectionstat, 'info': None}
        cards[card] = seconddictionary
    maindictionary['cards'] = cards
    return maindictionary


def connectionStatus(card):
    if card is None:
        netstate = "Network card is not enabled"
    elif 'wlan' in card:
        if ifWlanDisable(card) is False and ifStatue(card) is True:
            cmd1 = "ifconfig %s | grep ssid" % card
            cmd2 = "ifconfig %s | grep 'inet '" % card
            out1 = Popen(cmd1, shell=True, stdout=PIPE,
                         universal_newlines=True)
            out2 = Popen(cmd2, shell=True, stdout=PIPE,
                         universal_newlines=True)
            line1 = out1.stdout.read().strip()
            line2 = out2.stdout.read().strip()
            netstate = line1 + '\n' + subnetHexToDec(line2)
        else:
            netstate = "WiFi %s not connected" % card
    else:
        cmd = "ifconfig %s | grep 'inet '" % card
        out = Popen(cmd, shell=True, stdout=PIPE,
                    universal_newlines=True)
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
                os.system(f'service dhclient restart {card}')
                break
    return


def stopallnetwork():
    os.system('service netif stop')


def startallnetwork():
    os.system('service netif start')


def stopnetworkcard(netcard):
    os.system(f'service netif stop {netcard}')
    switch_default(netcard)


def restart_dhcp_network(netcard):
    os.system(f'service netif restart {netcard}')
    sleep(1)
    # os.system('service routing restart')
    # os.system(f'service dhclient restart {netcard}')


def start_static_network(netcard, inet, netmask):
    os.system(f'ifconfig {netcard} inet {inet} netmask {netmask}')
    sleep(1)
    os.system('service routing restart')


def startnetworkcard(netcard):
    os.system(f'service netif start {netcard}')
    sleep(1)
    os.system('service routing restart')
    os.system(f'service dhclient start {netcard}')


def wifiDisconnection(wificard):
    os.system(f'ifconfig {wificard} down')
    os.system(f"ifconfig {wificard} ssid 'none'")
    os.system(f'ifconfig {wificard} up')


def disableWifi(wificard):
    os.system(f'ifconfig {wificard} down')


def enableWifi(wificard):
    os.system(f'ifconfig {wificard} up')
    os.system(f'ifconfig {wificard} up scan')


def connectToSsid(name, wificard):
    os.system('killall wpa_supplicant')
    # service
    sleep(0.5)
    os.system(f"ifconfig {wificard} ssid '{name}'")
    sleep(0.5)
    wpa_supplicant = run(
        f'wpa_supplicant -B -i {wificard} -c /etc/wpa_supplicant.conf',
        shell=True
    )
    if wpa_supplicant.returncode != 0:
        return False
    return True


def subnetHexToDec(ifconfigstring):
    snethex = re.search('0x.{8}', ifconfigstring).group(0)[2:]
    snethexlist = re.findall('..', snethex)
    snetdeclist = [int(li, 16) for li in snethexlist]
    snetdec = ".".join(str(li) for li in snetdeclist)
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


def wlan_status(card):
    out = Popen(
        f'ifconfig {card} | grep status:',
        shell=True, stdout=PIPE,
        universal_newlines=True
    )
    return out.stdout.read().split(':')[1].strip()


def start_dhcp(wificard):
    os.system(f'dhclient {wificard}')
