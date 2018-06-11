#!/usr/bin/evn python
"""
Copyright (c) 2014-2016, GhostBSD. All rights reserved.

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

from subprocess import Popen, PIPE, STDOUT, call
from sys import path
import os.path
import re

path.append("/usr/local/share/networkmgr")
ncard = 'ifconfig -l'
notnics = ["lo", "fwe", "fwip", "tap", "plip", "pfsync", "pflog",
           "tun", "sl", "faith", "ppp", "brige", "ixautomation"]


if os.path.exists("/sbin/openrc") is True:
    openrc = True
else:
    openrc = False


def scanWifiBssid(bssid, wificard):
    grepListScanv = "ifconfig -v %s list scan | grep -a %s" % (wificard, bssid)
    wifi = Popen(grepListScanv, shell=True, stdout=PIPE, close_fds=True,
                 universal_newlines=True)
    info = wifi.stdout.readlines()[0].rstrip()
    return info


def ifnetworkup():
    pass


def wlan_list():
    crd = Popen(ncard, shell=True, stdout=PIPE, close_fds=True,
                universal_newlines=True)
    wlanlist = []
    for wlan in crd.stdout.readlines()[0].rstrip().split(' '):
        if "wlan" in wlan:
            wlanlist.append(wlan)
    return wlanlist


def wired_list():
    crd = Popen(ncard, shell=True, stdout=PIPE, close_fds=True,
                universal_newlines=True)
    wiredlist = []
    for wiredcn in crd.stdout.readlines()[0].rstrip().split(' '):
        wnc = wiredcn
        wcardn = re.sub(r'\d+', '', wiredcn)
        if wcardn not in notnics:
            wiredlist.append(wnc)
    return wiredlist


def ifwificardadded():
    wifis = 'sysctl -in net.wlan.devices'
    wifinics = Popen(wifis, shell=True, stdout=PIPE, close_fds=True,
                     universal_newlines=True)
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


def bssidsn(bssid, wificard):
    grepListScanv = "ifconfig -v %s list scan | grep -a %s" % (wificard, bssid)
    wifi = Popen(grepListScanv, shell=True, stdout=PIPE, close_fds=True,
                 universal_newlines=True)
    info = wifi.stdout.readlines()
    if len(info) == 0:
        return 0
    else:
        newline = info[0][33:]
        bssidlist = newline.split(' ')
        bssidlist = list(filter(None, bssidlist))
        return barpercent(bssidlist[3])


def scanSsid(ssid, wificard):
    grepListScanv = "ifconfig -v %s list scan | grep %s" % (wificard, ssid)
    wifi = Popen(grepListScanv, shell=True, stdout=PIPE, close_fds=True,
                 universal_newlines=True)
    info = wifi.stdout.readlines()[0].rstrip().split(' ')
    info = list(filter(None, info))
    return info


def wiredonlineinfo():
    for netcard in wired_list():
        lan = Popen('ifconfig ' + netcard, shell=True,
                    stdout=PIPE, close_fds=True, universal_newlines=True)
        if 'inet ' in lan.stdout.read():
            isonlin = True
            break
        else:
            isonlin = False
    return isonlin


def ifcardisonline(netcard):
    lan = Popen('ifconfig ' + netcard, shell=True,
                stdout=PIPE, close_fds=True, universal_newlines=True)
    if 'inet ' in lan.stdout.read():
        return True
    else:
        return False


def ifWlanInRc():
    rc_conf = open('/etc/rc.conf', 'r').read()
    if 'wlan' in rc_conf:
        return True
    else:
        return False


def ifWlan():
    nics = Popen(ncard, shell=True, stdout=PIPE, close_fds=True,
                 universal_newlines=True)
    if "wlan" in nics.stdout.read():
        return True
    else:
        return False


def defaultcard():
    cmd = "netstat -r | grep default"
    nics = Popen(cmd, shell=True, stdout=PIPE, close_fds=True,
                 universal_newlines=True)
    device = nics.stdout.readlines()
    if len(device) == 0:
        return None
    else:
        return list(filter(None, device[0].rstrip().split()))[3]


def ifWlanDisable(wificard):
    cmd = "ifconfig %s list scan" % wificard
    nics = Popen(cmd, shell=True, stdout=PIPE, close_fds=True,
                 universal_newlines=True)
    if "" == nics.stdout.read():
        return True
    else:
        return False


def ifStatue(wificard):
    cmd = "ifconfig %s" % wificard
    wl = Popen(cmd, shell=True, stdout=PIPE, close_fds=True,
               universal_newlines=True)
    wlout = wl.stdout.read()
    if "associated" in wlout:
        return True
    else:
        return False


def get_ssid(wificard):
    wlan = Popen('ifconfig %s | grep ssid' % wificard,
                 shell=True, stdout=PIPE, close_fds=True,
                 universal_newlines=True)
    return wlan.stdout.readlines()[0].rstrip().split()[1]


def get_bssid(wificard):
     wlan = Popen('ifconfig -v %s | grep bssid' % wificard,
                 shell=True, stdout=PIPE, close_fds=True,
                 universal_newlines=True)
     return wlan.stdout.readlines()[0].rstrip().split()[-1]


def networklist():
    crd = Popen(ncard, shell=True, stdout=PIPE, close_fds=True,
                universal_newlines=True)
    devicelist = []
    for deviced in crd.stdout.readlines()[0].rstrip().split(' '):
        ndev = deviced
        card = re.sub(r'\d+', '', deviced)
        if card not in notnics:
            devicelist.append(ndev)
    return devicelist


def ifcardconnected(netcard):
    wifi = Popen('ifconfig ' + netcard,
                 shell=True, stdin=PIPE, stdout=PIPE,
                 stderr=STDOUT, close_fds=True, universal_newlines=True)
    if 'status: active' in wifi.stdout.read():
        return True
    else:
        return False


def barpercent(sn):
    sig = int(sn.partition(':')[0])
    noise = int(sn.partition(':')[2])
    return int((sig - noise) * 4)


def networkdictionary():
    nlist = networklist()
    maindictionary = {}
    for card in nlist:
        if 'wlan' in card:
            scanv = "ifconfig -v %s list scan | grep -va BSSID" % card
            wifi = Popen(scanv, shell=True, stdin=PIPE,
                         stdout=PIPE, stderr=STDOUT, close_fds=True,
                         universal_newlines=True)
            conectioninfo = {}
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
                conectioninfo[bssid] = info
            if ifWlanDisable(card) is True:
                conectionstat = {"conection": "Disabled", "ssid": None, "bssid": None}
            elif ifStatue(card) is False:
                conectionstat = {"conection": "Disconnected", "ssid": None, "bssid": None}
            else:
                ssid = get_ssid(card)
                bssid = get_bssid(card)
                conectionstat = {"conection": "Connected",
                                 "ssid": ssid,
                                 "bssid": bssid}
            seconddictionary = {'state': conectionstat, 'info': conectioninfo}
        else:
            if ifcardisonline(card) is True:
                conectionstat = {"conection": "Connected"}
            elif ifcardconnected(card) is True:
                conectionstat = {"conection": "Disconnected"}
            else:
                conectionstat = {"conection": "Unplug"}
            seconddictionary = {'state': conectionstat, 'info': None}
        maindictionary[card] = seconddictionary
    return maindictionary


def stopallnetwork():
    if openrc is True:
        call('doas service network stop', shell=True)
    else:
        call('doas service netif stop', shell=True)


def startallnetwork():
    if openrc is True:
        call('doas service network start', shell=True)
    else:
        call('doas service netif start', shell=True)

def restartnetworkcard(netcard):
    if openrc is True:
        call('doas service network.%s restart ' % netcard, shell=True)
    else:
        call('doas service netif restart %s' % netcard, shell=True)


def stopnetworkcard(netcard):
    if openrc is True:
        call('doas service network.%s stop' % netcard, shell=True)
    else:
        call('doas service netif stop %s' % netcard, shell=True)


def startnetworkcard(netcard):
    if openrc is True:
        call('doas service network.%s start ' % netcard, shell=True)
    else:
        call('doas service netif start %s' % netcard, shell=True)


def wifiDisconnection(wificard):
    call('doas ifconfig %s down' % wificard, shell=True, close_fds=True)
    call('doas ifconfig %s up scan'  % wificard, shell=True, close_fds=True)
    call('doas ifconfig %s up scan' % wificard, shell=True, close_fds=True)


def disableWifi(wificard):
    call('doas ifconfig %s down' % wificard, shell=True, close_fds=True)


def enableWifi(wificard):
    call('doas ifconfig %s up scan' % wificard, shell=True, close_fds=True)
    call('doas ifconfig %s up scan' % wificard, shell=True, close_fds=True)
    if openrc is True:
        call('doas service wpa_supplicant.%s restart ' % wificard, shell=True)
    else:
        call('doas service wpa_supplicant restart %s' % wificard, shell=True)


def connectToSsid(name, wificard):
    # call('doas service netif restart wlan0', shell=True
    call("doas ifconfig %s ssid '%s'" % (wificard, name), shell=True)
    if openrc is True:
        call('doas service network.%s restart ' % wificard, shell=True)
    else:
        call('doas service netif restart %s' % wificard, shell=True)


def conectionStatus():
    if ifWlan() is True:
        if ifWlanDisable() is False:
            cmd = "ifconfig wlan0 | grep ssid"
            out = Popen(cmd, shell=True, stdout=PIPE, close_fds=True,
                        universal_newlines=True)
            netstate = out.stdout.read().strip()
        else:
            netstate = "Network Manager"
    else:
        netstate = "Network Manager"
    return netstate


### adding a fuction to see if wlan did crash after resuming suspend.
