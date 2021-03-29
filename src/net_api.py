#!/usr/bin/env python3
"""
Copyright (c) 2014-2019, GhostBSD. All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

1. Redistribution's of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.

2. Redistribution's in binary form must reproduce the above
   copyright notice,this list of conditions and the following
   disclaimer in the documentation and/or other materials provided
   with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES(INCLUDING,
BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
"""

from subprocess import Popen, PIPE
from sys import path
import os
import re
from time import sleep
path.append("/usr/local/share/networkmgr")

not_nics = [
    "lo",
    "fwe",
    "fwip",
    "tap",
    "plip",
    "pfsync",
    "pflog",
    "tun",
    "sl",
    "faith",
    "ppp",
    "brige",
    "ixautomation",
    "vm-ixautomation",
    "vm-public",
    "wg"
]

cmd = "kenv | grep rc_system"
rc_system = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)

if 'openrc' in rc_system.stdout.read():
    openrc = True
    rc = 'rc-'
    network = 'network'
else:
    openrc = False
    rc = ''
    network = 'netif'


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


def networklist():
    crd = Popen('ifconfig -l', shell=True, stdout=PIPE, universal_newlines=True)
    card_list = crd.stdout.read().strip().split()
    re_compile = re.compile(("|".join(not_nics)))
    bad_list = list(filter(re_compile.match, card_list))
    return list(set(card_list).difference(bad_list))


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
    if openrc is True:
        status = Popen(
            f'{rc}service {network} status',
            shell=True,
            stdout=PIPE,
            universal_newlines=True
        )
        if 'status: started' in status.stdout.read():
            return True
        else:
            return False
    else:
        return False


def networkdictionary():
    nlist = networklist()
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
            netstate = "WiFi %s not conected" % card
    else:
        cmd = "ifconfig %s | grep 'inet '" % card
        out = Popen(cmd, shell=True, stdout=PIPE,
                    universal_newlines=True)
        line = out.stdout.read().strip()
        netstate = subnetHexToDec(line)
    return netstate


def stopallnetwork():
    os.system(f'{rc}service {network} stop')


def startallnetwork():
    os.system(f'{rc}service {network} start')


def stopnetworkcard(netcard):
    os.system(f'ifconfig {netcard} down')


def startnetworkcard(netcard):
    if openrc is True:
        os.system(f'dhcpcd {netcard}')
    else:
        os.system(f'dhclient {netcard}')


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
    sleep(0.5)
    os.system(f"ifconfig {wificard} ssid '{name}'")
    sleep(0.5)
    os.system(f'wpa_supplicant -B -i {wificard} -c /etc/wpa_supplicant.conf')
    if openrc is True:
        os.system(f'dhcpcd {wificard}')
    else:
        os.system(f'dhclient {wificard}')


def subnetHexToDec(ifconfigstring):
    snethex = re.search('0x.{8}', ifconfigstring).group(0)[2:]
    snethexlist = re.findall('..', snethex)
    snetdeclist = [int(li, 16) for li in snethexlist]
    snetdec = ".".join(str(li) for li in snetdeclist)
    outputline = ifconfigstring.replace(re.search('0x.{8}', ifconfigstring).group(0), snetdec)
    return outputline
