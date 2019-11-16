#!/usr/bin/env python3.6
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
ncard = 'ifconfig -l'
notnics = ["lo", "fwe", "fwip", "tap", "plip", "pfsync", "pflog",
           "tun", "sl", "faith", "ppp", "brige", "ixautomation"]

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


def scanWifiBssid(bssid, wificard):
    grepListScanv = "ifconfig -v %s list scan | grep -a %s" % (wificard, bssid)
    wifi = Popen(grepListScanv, shell=True, stdout=PIPE,
                 universal_newlines=True)
    info = wifi.stdout.readlines()[0].rstrip()
    return info


def wired_list():
    crd = Popen(ncard, shell=True, stdout=PIPE, universal_newlines=True)
    wiredlist = []
    for wiredcn in crd.stdout.readlines()[0].rstrip().split(' '):
        wnc = wiredcn
        wcardn = re.sub(r'\d+', '', wiredcn)
        if wcardn not in notnics:
            wiredlist.append(wnc)
    return wiredlist


def ifwificardadded():
    wifis = 'sysctl -in net.wlan.devices'
    wifinics = Popen(wifis, shell=True, stdout=PIPE, universal_newlines=True)
    wifiscards = wifinics.stdout.readlines()
    answer = False
    if len(wifiscards) != 0:
        ifwifi = wifiscards[0].rstrip()
        rc_conf = open('/etc/rc.conf', 'r').read()
        wificardlist = ifwifi.split()
        for wfcard in wificardlist:
            if 'wlans_%s=' % wfcard not in rc_conf:
                answer = True
                break
    return answer


def ifwiredcardadded():
    cardlist = wired_list()
    answer = False
    if len(cardlist) != 0:
        rc_conf = open('/etc/rc.conf', 'r').read()
        for card in cardlist:
            if 'ifconfig_%s=' % card not in rc_conf:
                answer = True
                break
    return answer


def isanewnetworkcardinstall():
    if ifwificardadded() is True or ifwiredcardadded() is True:
        return True
    else:
        return False


def ifcardisonline(netcard):
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


def get_bssid(wificard):
    wlan = Popen('ifconfig -v %s | grep bssid' % wificard,
                 shell=True, stdout=PIPE, universal_newlines=True)
    return wlan.stdout.readlines()[0].rstrip().split()[-1]


def networklist():
    crd = Popen(ncard, shell=True, stdout=PIPE, universal_newlines=True)
    devicelist = []
    for deviced in crd.stdout.readlines()[0].rstrip().split(' '):
        ndev = deviced
        card = re.sub(r'\d+', '', deviced)
        if card not in notnics:
            devicelist.append(ndev)
    return devicelist


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
            scanv = "ifconfig -v %s list scan | grep -va BSSID" % card
            wifi = Popen(scanv, shell=True, stdout=PIPE,
                         universal_newlines=True)
            connectioninfo = {}
            for line in wifi.stdout:
                if line[0] == " ":
                    ssid = "Unknown"
                    newline = line[:83]
                else:
                    ssid = line[:33].strip()
                    newline = line[:83].strip()
                info = newline[33:].split(' ')
                info = list(filter(None, info))
                sn = info[3]
                bssid = info[0]
                info[3] = barpercent(sn)
                info.insert(0, ssid)
                connectioninfo[bssid] = info
            if ifWlanDisable(card) is True:
                connectionstat = {
                    "connection": "Disabled",
                    "ssid": None,
                    "bssid": None
                }
            elif ifStatue(card) is False:
                connectionstat = {
                    "connection": "Disconnected",
                    "ssid": None, "bssid": None
                }
            else:
                ssid = get_ssid(card)
                bssid = get_bssid(card)
                connectionstat = {
                    "connection": "Connected",
                    "ssid": ssid,
                    "bssid": bssid
                }
            seconddictionary = {
                'state': connectionstat,
                'info': connectioninfo
            }
        else:
            if ifcardisonline(card) is True:
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
        netstate = "No network card enable"
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
            netstate = line1 + '\n' + line2
        else:
            netstate = "WiFi %s not conected" % card
    else:
        cmd = "ifconfig %s | grep 'inet '" % card
        out = Popen(cmd, shell=True, stdout=PIPE,
                    universal_newlines=True)
        line = out.stdout.read().strip()
        netstate = line
    return netstate


def stopallnetwork():
    os.system(f'doas {rc}service {network} stop')
    sleep(1)


def startallnetwork():
    os.system(f'doas {rc}service {network} start')
    sleep(1)


def stopnetworkcard(netcard):
    os.system(f'doas ifconfig {netcard} down')
    sleep(1)


def startnetworkcard(netcard):
    os.system(f'doas ifconfig {netcard} up')
    sleep(1)


def wifiDisconnection(wificard):
    os.system(f'doas ifconfig {wificard} down')
    os.system(f"doas ifconfig {wificard} ssid 'none'")
    os.system(f'doas ifconfig {wificard} up')
    sleep(1)


def disableWifi(wificard):
    os.system(f'doas ifconfig {wificard} down')
    sleep(1)


def enableWifi(wificard):
    os.system(f'doas ifconfig {wificard} up')
    os.system(f'doas ifconfig {wificard} up scan')
    sleep(1)

# work around of iwm on FreeBSD 12.0
def start_wifi():
   for nic in ncard.split():
       if 'wlan' in nic:
           os.system(f'doas wpa_supplicant -B -i {nic} -c /etc/wpa_supplicant.conf')
           sleep(0.5)
           os.system(f'doas ifconfig {nic} up')
           sleep(0.5)
           os.system(f'doas ifconfig {nic} scan')
           sleep(2)
           os.system(f'doas dhclient {nic}')
           
   


def connectToSsid(name, wificard):
    os.system(f'doas killall wpa_supplicant')
    sleep(0.5)
    os.system(f"doas ifconfig {wificard} ssid '{name}'")
    sleep(0.5)
    os.system(f'doas wpa_supplicant -B -i {wificard} -c /etc/wpa_supplicant.conf')
    sleep(0.5)
    os.system(f'doas ifconfig {wificard} up')
    sleep(0.5)
    os.system(f'doas ifconfig {wificard} scan')
    sleep(2)
    os.system(f'doas dhclient {wificard}')
    sleep(0.5)
