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
path.append("/usr/local/share/networkmgr")
ncard = 'doas detect-nics'
detect_wifi = 'doas detect-wifi'
scan = "ifconfig wlan0 list scan | grep -v SSID"
scanv = "ifconfig -v wlan0 list scan | grep -va BSSID"
grepListScan = "ifconfig wlan0 list scan | grep -a "
grepListScanv = "ifconfig -v wlan0 list scan | grep -a "
grepScan = "doas ifconfig wlan0 scan | grep -a "


def scanWifiBssid(bssid):
    wifi = Popen(grepListScan + bssid, shell=True, stdout=PIPE, close_fds=True)
    info = wifi.stdout.readlines()[0].rstrip().split(' ')
    info = filter(None, info)
    return info


def bssidsn(bssid):
    wifi = Popen(grepListScanv + bssid, shell=True, stdout=PIPE, close_fds=True)
    info = wifi.stdout.readlines()
    if len(info) == 0:
        return 0
    else:
        newline = info[0][33:]
        bssidlist = newline.split(' ')
        bssidlist = filter(None, bssidlist)
        return barpercent(bssidlist[3])


def scanSsid(ssid):
    wifi = Popen(grepListScanv + ssid, shell=True, stdout=PIPE, close_fds=True)
    info = wifi.stdout.readlines()[0].rstrip().split(' ')
    info = filter(None, info)
    return info


def wirecard():
    wireNics = Popen('cat /etc/rc.conf | grep ifconfig_ | grep -v wlan',
                     shell=True, stdout=PIPE, close_fds=True)
    # for line in wireNics.stdout:
    card = wireNics.stdout.readlines()[0].partition('=')[0].partition('_')[2]
    return card


def wiredonlineinfo():
    lan = Popen('doas ifconfig ' + wirecard(), shell=True,
                stdout=PIPE, close_fds=True)
    if 'inet' in lan.stdout.read():
        return True
    else:
        return False


def ifWlanInRc():
    rc_conf = open('/etc/rc.conf', 'r').read()
    if 'wlan0' in rc_conf:
        return True
    else:
        return False


def ifWlan():
        cmd = "doas ifconfig wlan0"
        nics = Popen(cmd, shell=True, stdout=PIPE, close_fds=True)
        if "wlan0" in nics.stdout.read():
            return True
        else:
            return False


def ifWlanDisable():
        cmd = "doas ifconfig wlan0 list scan"
        nics = Popen(cmd, shell=True, stdout=PIPE, close_fds=True)
        if "" == nics.stdout.read():
            return True
        else:
            return False


def ifStatue():
    cmd = "doas ifconfig wlan0"
    wl = Popen(cmd, shell=True, stdout=PIPE, close_fds=True)
    wlout = wl.stdout.read()
    if "associated" in wlout:
        return True
    else:
        return False


def get_ssid():
    if ifWlan() is False:
        return None
    else:
        wlan = Popen('doas ifconfig wlan0 | grep ssid',
                     shell=True, stdout=PIPE, close_fds=True)
        return wlan.stdout.readlines()[0].rstrip().split()[1]


def netstate():
    if ifWlan() is False and wiredonlineinfo() is False:
        state = None
    elif ifWlan() is False and wiredonlineinfo() is True:
        state = 200
    elif ifStatue() is False and wiredonlineinfo() is True:
        state = 200
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


def wifiListe():
    wifi = Popen(scanv, shell=True, stdin=PIPE,
                 stdout=PIPE, stderr=STDOUT, close_fds=True)
    wlist = []
    for line in wifi.stdout:
        if line[0] == " ":
            ssid = ["Unknown"]
            newline = line[33:]
        else:
            ssid = [line[:33].strip()]
            newline = line[33:]
        info = newline.split(' ')
        info = filter(None, info)
        newinfo = ssid + info
        wlist.append(newinfo)
    return wlist


def barpercent(sn):
    sig = int(sn.partition(':')[0])
    noise = int(sn.partition(':')[2])
    bar = (sig - noise) * 4
    return bar


def lockinfo(ssid):
    wifi = Popen('doas ifconfig wlan0 list scan',
                 shell=True, stdin=PIPE,
                 stdout=PIPE, stderr=STDOUT, close_fds=True)
    linfo = []
    for line in wifi.stdout:
        if line[0] == " ":
            line = "Unknown" + line
        if ssid in line:
            linfo = line
    return linfo


def wiredconnectedinfo():
    wifi = Popen('doas ifconfig ' + wirecard(),
                 shell=True, stdin=PIPE, stdout=PIPE,
                 stderr=STDOUT, close_fds=True)
    if 'status: active' in wifi.stdout.read():
        return True
    else:
        return False


def stopallnetwork():
    call('doas service netif stop', shell=True)


def startallnetwork():
    call('doas service netif restart', shell=True)
    nics = Popen(ncard, shell=True, stdout=PIPE, close_fds=True)
    if "wlan0" in nics.stdout.read():
        call('doas wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant.conf',
             shell=True)


def stopwirednetwork():
    call('doas service netif stop ' + wirecard(), shell=True)


def startwirednetwork():
    call('doas service netif start ' + wirecard(), shell=True)


def wifiDisconnection():
    call('doas ifconfig wlan0 down', shell=True, close_fds=True)
    call('doas ifconfig wlan0 up scan', shell=True, close_fds=True)
    call('doas ifconfig wlan0 up scan', shell=True, close_fds=True)


def wifiConnection():
    call('doas ifconfig wlan0 up', shell=True)
    call("doas service netif restart wlan0", shell=True)


def disableWifi():
    call('doas ifconfig wlan0 down', shell=True, close_fds=True)


def enableWifi():
    call('doas ifconfig wlan0 up scan', shell=True, close_fds=True)
    call('doas ifconfig wlan0 up scan', shell=True, close_fds=True)
    #call('doas wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant.conf',
    #     shell=True)


def connectToSsid(name):
    # call('doas service netif restart wlan0', shell=True)
    call('doas ifconfig wlan0 ssid %s' % name, shell=True)
    call('doas wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant.conf',
         shell=True)


def conectionStatus():
    if ifWlan() is True:
        if ifWlanDisable() is False:
            cmd = "ifconfig wlan0 | grep ssid"
            out = Popen(cmd, shell=True, stdout=PIPE, close_fds=True)
            netstate = out.stdout.read().strip()
        else:
            netstate = "Network Manager"
    else:
        netstate = "Network Manager"
    return netstate

