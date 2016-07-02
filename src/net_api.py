#!/usr/local/bin/python
from subprocess import Popen, PIPE, STDOUT, call
# import re
# import os
from sys import path
path.append("/usr/local/share/networkmgr")
ncard = 'sudo operator sh /usr/local/share/networkmgr/detect-nics.sh'
detect_wifi = 'sudo operator sh /usr/local/share/networkmgr/detect-wifi.sh'
scan = "ifconfig wlan0 list scan | grep -v SSID"
scanv = "ifconfig -v wlan0 list scan | grep -v SSID/"
grepListScan = "ifconfig wlan0 list scan | grep "
grepScan = "sudo operator ifconfig wlan0 scan | grep "


def scanWifiBssid(bssid):
    wifi = Popen(grepListScan + bssid, shell=True, stdout=PIPE, close_fds=True)
    info = wifi.stdout.readlines()[0].rstrip().split(' ')
    info = filter(None, info)
    return info


def scanSsid(ssid):
    wifi = Popen(grepScan + ssid, shell=True, stdout=PIPE, close_fds=True)
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
    lan = Popen('sudo operator ifconfig ' + wirecard(), shell=True,
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
        cmd = "sudo operator ifconfig wlan0"
        nics = Popen(cmd, shell=True, stdout=PIPE, close_fds=True)
        if "wlan0" in nics.stdout.read():
            return True
        else:
            return False


def ifWlanDisable():
        cmd = "sudo operator ifconfig wlan0 list scan"
        nics = Popen(cmd, shell=True, stdout=PIPE, close_fds=True)
        if "" == nics.stdout.read():
            return True
        else:
            return False


def ifStatue():
    cmd = "sudo operator ifconfig wlan0"
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
        wlan = Popen('sudo operator ifconfig wlan0 | grep ssid',
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
            line = "Unknown" + line
        info = line.split(' ')
        info = filter(None, info)
        wlist.append(info)
    return wlist

def barpercent(sn):
    sig = int(sn.partition(':')[0])
    noise = int(sn.partition(':')[2])
    bar = (sig - noise) * 4
    return bar


def lockinfo(ssid):
    wifi = Popen('sudo operator ifconfig wlan0 list scan',
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
    wifi = Popen('sudo operator ifconfig ' + wirecard(),
                 shell=True, stdin=PIPE, stdout=PIPE,
                 stderr=STDOUT, close_fds=True)
    if 'status: active' in wifi.stdout.read():
        return True
    else:
        return False


def stopallnetwork():
    call('sudo operator /etc/rc.d/netif stop', shell=True)


def startallnetwork():
    call('sudo operator /etc/rc.d/netif restart', shell=True)
    nics = Popen(ncard, shell=True, stdout=PIPE, close_fds=True)
    if "wlan0" in nics.stdout.read():
        call('sudo operator wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant.conf',
             shell=True)


def stopwirednetwork():
    call('sudo operator /etc/rc.d/netif stop ' + wirecard(), shell=True)


def startwirednetwork():
    call('sudo operator /etc/rc.d/netif start ' + wirecard(), shell=True)


def wifiDisconnection():
    call('sudo operator ifconfig wlan0 down', shell=True, close_fds=True)
    call('sudo operator ifconfig wlan0 up scan', shell=True, close_fds=True)
    call('sudo operator ifconfig wlan0 up scan', shell=True, close_fds=True)


def wifiConnection():
    call('sudo operator ifconfig wlan0 up', shell=True)
    call("sudo operator service netif restart wlan0", shell=True)


def disableWifi():
    call('sudo operator ifconfig wlan0 down', shell=True, close_fds=True)


def enableWifi():
    call('sudo operator ifconfig wlan0 up scan', shell=True, close_fds=True)
    call('sudo operator ifconfig wlan0 up scan', shell=True, close_fds=True)
    #call('sudo operator wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant.conf',
    #     shell=True)


def connectToSsid(name):
    # call('sudo operator service netif restart wlan0', shell=True)
    call('sudo operator ifconfig wlan0 ssid %s' % name, shell=True)
    call('sudo operator wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant.conf',
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

