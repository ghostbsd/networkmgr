#!/usr/local/bin/python
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
           "tun", "sl", "faith", "ppp", "wlan", "brige", "ixautomation"]


if os.path.exists("/sbin/openrc") is True:
    openrc = True
    start_network = 'doas service network start'
    stop_network = 'doas service network stop'
else:
    openrc = False
    start_network = 'doas service netif start'
    stop_network = 'doas service netif stop'


def scanWifiBssid(bssid, wificard):
    grepListScanv = "ifconfig -v %s list scan | grep -a %s" % (wificard, bssid) 
    wifi = Popen(grepListScanv, shell=True, stdout=PIPE, close_fds=True,
                 universal_newlines=True)
    info = wifi.stdout.readlines()[0].rstrip().split(' ')
    info = list(filter(None, info))
    return info


def wlan_list():
    crd = Popen(ncard, shell=True, stdout=PIPE,close_fds=True,
                universal_newlines=True)
    wlanlist = []
    for wlan in crd.stdout.readlines()[0].rstrip().split(' '):
        if "wlan" in wlan:
            wlanlist.append(wlan)
    return wlanlist


def wired_list():
    crd = Popen(ncard, shell=True, stdout=PIPE,close_fds=True,
                universal_newlines=True)
    wiredlist = []
    for wiredcn in crd.stdout.readlines()[0].rstrip().split(' '):
        wnc = wiredcn
        wcardn = re.sub(r'\d+', '', wiredcn)
        if wcardn not in notnics:
            wiredlist.append(wnc)
    return wiredlist


def bssidsn(bssid, wificard):
    grepListScanv = "ifconfig -v %s list scan | grep -a %s" % (wificard, bssid)  
    wifi = Popen(grepListScanv, shell=True, stdout=PIPE,close_fds=True,
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
    grepListScanv = "ifconfig -v %s list scan | grep -a %s" % (wificard, ssid) 
    wifi = Popen(grepListScanv + ssid, shell=True, stdout=PIPE, close_fds=True,
                 universal_newlines=True)
    info = wifi.stdout.readlines()[0].rstrip().split(' ')
    info = list(filter(None, info))
    return info


def wiredonlineinfo():
    for netcard in wired_list(): 
        lan = Popen('doas ifconfig ' + netcard, shell=True,
                    stdout=PIPE, close_fds=True, universal_newlines=True)
        if 'inet' in lan.stdout.read():
            isonlin = True
            break
        else:
            isonlin = False
    return isonlin

def ifcardisonline(netcard):
    lan = Popen('doas ifconfig ' + netcard, shell=True,
                stdout=PIPE, close_fds=True, universal_newlines=True)
    if 'inet' in lan.stdout.read():
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


def ifWlanDisable(wificard):
    if ifWlan() is True:
        cmd = "doas ifconfig %s list scan" % wificard
        nics = Popen(cmd, shell=True, stdout=PIPE, close_fds=True,
                universal_newlines=True)
        if "" == nics.stdout.read():
            return True
        else:
            return False
    else:
        return True


def ifStatue(wificard):
    if ifWlan() is True:
        cmd = "doas ifconfig %s" % wificard
        wl = Popen(cmd, shell=True, stdout=PIPE, close_fds=True,
                universal_newlines=True)
        wlout = wl.stdout.read()
        if "associated" in wlout:
            return True
        else:
            return False
    else:
        return False


def get_ssid(wificard):
    wlan = Popen('doas ifconfig %s | grep ssid' % wificard,
                 shell=True, stdout=PIPE, close_fds=True,
                 universal_newlines=True)
    return wlan.stdout.readlines()[0].rstrip().split()[1]


def netstate():
    if wiredonlineinfo() is True:
        state = 200
    elif ifWlan() is False and wiredonlineinfo() is False:
        state = None
    elif ifStatue() is False and wiredonlineinfo() is False:
        state = None
    else:
        ssid = get_ssid()
        scn = scanSsid(ssid)
        sn = scn[4]
        sig = int(sn.partition(':')[0])
        noise = int(sn.partition(':')[2])
        state = (sig - noise) * 4
    return state


def wifiListe(wificard):
    scanv = "ifconfig -v %s list scan | grep -va BSSID" % wificard
    wifi = Popen(scanv, shell=True, stdin=PIPE,
                 stdout=PIPE, stderr=STDOUT, close_fds=True,
                 universal_newlines=True)
    wlist = []
    for line in wifi.stdout:
        if line[0] == " ":
            ssid = ["Unknown"]
            newline = line[33:]
        else:
            ssid = [line[:33].strip()]
            newline = line[33:]
        info = newline.split(' ')
        info = list(filter(None, info))
        newinfo = ssid + info
        wlist.append(newinfo)
    return wlist


def barpercent(sn):
    sig = int(sn.partition(':')[0])
    noise = int(sn.partition(':')[2])
    bar = (sig - noise) * 4
    return bar


def lockinfo(ssid, wificard):
    wifi = Popen('doas ifconfig %s list scan' % wificard, shell=True, 
                 stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True,
                 universal_newlines=True)
    linfo = []
    for line in wifi.stdout:
        if line[0] == " ":
            line = "Unknown" + line
        if ssid in line:
            linfo = line
    return linfo


def ifcardconnected(netcard):
    wifi = Popen('doas ifconfig ' + netcard,
                 shell=True, stdin=PIPE, stdout=PIPE,
                 stderr=STDOUT, close_fds=True, universal_newlines=True)
    if 'status: active' in wifi.stdout.read():
        return True
    else:
        return False

def stopallnetwork():
    call(stop_network, shell=True)


def startallnetwork():
    call(start_network, shell=True)


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
    call('doas ifconfig %s up scan' % wificard, shell=True, close_fds=True)
    call('doas ifconfig %s up scan' % wificard, shell=True, close_fds=True)


def disableWifi(wificard):
    call('doas ifconfig %s down' % wificard, shell=True, close_fds=True)


def enableWifi(wificard):
    call('doas ifconfig %s up scan' % wificard, shell=True, close_fds=True)
    call('doas ifconfig %s up scan' % wificard, shell=True, close_fds=True)
    if openrc is True:
        call('doas service network.%s restart ' % wificard, shell=True)
    else:
        call('doas service netif restart %s' % wificard, shell=True)
    #call('doas wpa_supplicant -B -i %s -c /etc/wpa_supplicant.conf' % wificard, shell=True)


def connectToSsid(name, wificard):
    # call('doas service netif restart wlan0', shell=True)
    call("doas ifconfig %s ssid '%s'" % (wificard, name), shell=True)
    if openrc is True:
        call('doas service network.%s restart ' % wificard, shell=True)
    else:
        call('doas service netif restart %s' % wificard, shell=True)
    #call('doas wpa_supplicant -B -i %s -c /etc/wpa_supplicant.conf' % wificard, shell=True)


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
