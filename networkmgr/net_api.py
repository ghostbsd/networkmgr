#!/usr/local/bin/python

from subprocess import Popen, PIPE, STDOUT, call
#import re
#import os
ncard = 'sh detect-nics.sh'
detect_wifi = 'sh detect-wifi.sh'
scan = "ifconfig wlan0 up list scan"


def scanWifiSsid(ssid):
    wifi = Popen(scan, shell=True, stdout=PIPE, close_fds=True)
    for line in wifi.stdout:
        if line[0] == " ":
            line = "Unknown" + line
        info = line.split('  ')
        info = filter(None, info)
        if ssid == info[0]:
            wnet = info
    return wnet


def wirecard():
    nics = Popen(ncard, shell=True, stdout=PIPE, close_fds=True)
    netcard = nics.stdout
    for line in netcard:
        card = line.rstrip().partition(' ')[0]
        if card != "wlan0":
            wifi = Popen("%s %s" % (detect_wifi, card), shell=True,
            stdout=PIPE, close_fds=True)
            answer = wifi.stdout.readlines()[0].strip()
            if answer == "yes":
                pass
            else:
                card0 = card
                break
    return card0


def wiredonlineinfo():
    wifi = Popen('ifconfig ' + wirecard(), shell=True, stdout=PIPE,
    close_fds=True)
    for line in wifi.stdout:
        if "inet" in line:
            answer = True
            break
        else:
            answer = None
    return answer


def netstate():
    if ifWlan() is None and wiredonlineinfo() is None:
        state = None
    elif ifWlan() is None and wiredonlineinfo() is True:
        state = 120
    elif get_ssid() == '""' and wiredonlineinfo() is True:
        state = 120
    elif get_ssid() == '""' and wiredonlineinfo() is None:
        state = 0
    else:
        ssid = get_ssid()
        scn = scanWifiSsid(ssid)
        if len(scn) == 7:
            sn = scn[4]
        else:
            sn = scn[3].rstrip().split()[1]
        sig = int(sn.partition(':')[0])
        noise = int(sn.partition(':')[2])
        state = (sig - noise) * 4
    return state


def find_rsn(info):
    var = False
    for line in info:
        if line == "RSN":
            var = True
    return var


def findWPA(info):
    var = False
    for line in info:
        if line == "WPA":
            var = True
    return var


def get_ssid():
    if ifWlan() is None:
        return None
    else:
        wlan = Popen('ifconfig wlan0', shell=True, stdout=PIPE, close_fds=True)
        for line in wlan.stdout:
            info = line.split()
            info2 = line.split('"')
            if "ssid" in info[0]:
                if '"' in line:
                    if info[1] == '""':
                        ssid = info[1]
                        break
                    else:
                        ssid = info2[1]
                        break
                else:
                    ssid = info[1]
        return ssid


def ifWlan():
        nics = Popen(ncard, shell=True, stdout=PIPE, close_fds=True)
        for line in nics.stdout.readlines():
            card = line.rstrip().partition(" ")[0]
            if card == "wlan0":
                answer = True
                break
            else:
                answer = None
        return answer


def ssidliste():
    wifi = Popen('ifconfig wlan0  list scan', shell=True, stdin=PIPE,
    stdout=PIPE, stderr=STDOUT, close_fds=True)
    b = False
    ssid = []
    for line in wifi.stdout:
        if line[0] == " ":
            line = "Unknown" + line
        info = line.split('   ')
        filter(None, info)
        if b is True:
            ssid.append(info[0])
        b = True
    return ssid


def barpercent(ssid):
    scn = scanWifiSsid(ssid)
    if len(scn) == 7:
        sn = scn[4]
    else:
        sn = scn[3].rstrip().split()[1]
    sig = int(sn.partition(':')[0])
    noise = int(sn.partition(':')[2])
    bar = (sig - noise) * 4
    return bar


def keyinfo(ssid):
    scn = scanWifiSsid(ssid)
    if len(scn) == 7:
        kinfo = scn[5].split()[1]
    else:
        kinfo = scn[4].split()[1]
    return kinfo


def openinfo(ssid):
    wifi = Popen('ifconfig wlan0  list scan', shell=True, stdin=PIPE,
    stdout=PIPE, stderr=STDOUT, close_fds=True)
    for line in wifi.stdout:
        if line[0] == " ":
            line = "Unknown" + line
        info = line.split('  ')
        if info[0] == ssid:
            return info[1].rstrip()


def lookinfo(ssid):
    wifi = Popen('ifconfig wlan0  list scan', shell=True, stdin=PIPE,
    stdout=PIPE, stderr=STDOUT, close_fds=True)
    linfo = []
    for line in wifi.stdout:
        if line[0] == " ":
            line = "Unknown" + line
        info = line.split()
        if info[0] == ssid:
            linfo.append(info[1])
            linfo.append(info[6])
            linfo.append(info[7])
            linfo.append(info[8])
            linfo.append(info[9])
            linfo.append(info[10])
    return linfo


def wiredconnectedinfo():
    wifi = Popen('ifconfig ' + wirecard(), shell=True, stdin=PIPE, stdout=PIPE,
    stderr=STDOUT, close_fds=True)
    for line in wifi.stdout:
        if "status: active" in line:
            return True


def stopallnetwork():
    call('/etc/rc.d/netif stop', shell=True)


def stopwirednetwork():
    call('/etc/rc.d/netif stop ' + wirecard(), shell=True)


def startallnetwork():
    call('/etc/rc.d/netif start', shell=True)
    call('service netif restart wlan0', shell=True)


def startwirednetwork():
    call('/etc/rc.d/netif start ' + wirecard(), shell=True)


def wifidisconnection():
    call('ifconfig wlan0 down', shell=True)
    call('ifconfig wlan0 up', shell=True)


def wificonnection():
    call('service netif restart wlan0', shell=True)
