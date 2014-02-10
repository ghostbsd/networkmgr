#!/usr/local/bin/python

from subprocess import Popen, PIPE, STDOUT, call
import re
import os
ncard = 'sh /usr/local/etc/gbi/backend-query/detect-nics.sh'
detect_wifi = 'sh /usr/local/etc/gbi/backend-query/detect-wifi.sh'


def wirecard():
    nics = Popen(ncard, shell=True, stdout=PIPE, close_fds=True)
    netcard = nics.stdout
    for line in netcard:
        card = line.rstrip().partition(':')[0]
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


def netstate():
    if os.path.exists("/etc/wpa_supplicant.conf"):
        wpa_supplican = open("/etc/wpa_supplicant.conf", 'r')
        if os.stat("/etc/wpa_supplicant.conf")[6] == 0:
            if wiredonlineinfo() is True:
                state = 120
            else:
                state = 110
        else:
            for line in wpa_supplican.readlines():
                info = line.strip()
                if info.partition('=')[0] == "ssid":
                    ssid = re.sub('["]', '', info.partition('=')[2])
            wifi = Popen('ifconfig wlan0  list scan', shell=True, stdin=PIPE,
            stdout=PIPE, stderr=STDOUT, close_fds=True)
            for line in wifi.stdout:
                info = line.split('   ')
                info = filter(None, info)
                if ssid == info[0]:
                    sn = info[3].rstrip().split()[1]
                    sig = int(sn.partition(':')[0])
                    noise = int(sn.partition(':')[2])
                    state = (sig - noise) * 4
    else:
        if wiredonlineinfo() is True:
            state = 120
        else:
            state = 110
    return state


def find_rsn(info):
    var = False
    for line in info:
        if line == "RSN":
            var = True
    return var


def get_ssid():
    if os.path.exists("/etc/wpa_supplicant.conf"):
        wpa_supplican = open("/etc/wpa_supplicant.conf", 'r')
        if os.stat("/etc/wpa_supplicant.conf")[6] == 0:
            ssid = None
        else:
            for line in wpa_supplican.readlines():
                info = line.strip()
                if info.partition('=')[0] == "ssid":
                    ssid = re.sub('["]', '', info.partition('=')[2])
    else:
        ssid = None
    return ssid


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
    wifi = Popen('ifconfig wlan0  list scan', shell=True, stdout=PIPE,
    close_fds=True)
    for line in wifi.stdout:
        if line[0] == " ":
            line = "Unknown" + line
        info = line.split("   ")
        info = filter(None, info)
        if ssid == info[0]:
            sn = info[3].rstrip().split()[1]
            sig = int(sn.partition(':')[0])
            noise = int(sn.partition(':')[2])
            bar = (sig - noise) * 4
    return bar


def keyinfo(ssid):
    wifi = Popen('ifconfig wlan0  list scan', shell=True, stdin=PIPE,
    stdout=PIPE, stderr=STDOUT, close_fds=True)
    for line in wifi.stdout:
        if line[0] == " ":
            line = "Unknown" + line
        info = line.split('   ')
        info = filter(None, info)
        if info[0] == ssid and len(info) == 5:
            kinfo = info[3].split()[3]
        elif info[0] == ssid and len(info) == 6:
            kinfo = info[4].split()[1]
    return kinfo


def openinfo(ssid):
    wifi = Popen('ifconfig wlan0  list scan', shell=True, stdin=PIPE,
    stdout=PIPE, stderr=STDOUT, close_fds=True)
    oinfo = []
    for line in wifi.stdout:
        if line[0] == " ":
            line = "Unknown" + line
        info = line.split('  ')
        if info[0] == ssid:
            oinfo.append(info[1])
            return oinfo


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


def wiredonlineinfo():
    wifi = Popen('ifconfig ' + wirecard(), shell=True, stdin=PIPE, stdout=PIPE,
    stderr=STDOUT, close_fds=True)
    for line in wifi.stdout:
        if "inet" in line:
            return True


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


def startwirednetwork():
    call('/etc/rc.d/netif start ' + wirecard(), shell=True)


def wifidisconnection():
    os.remove("/etc/wpa_supplicant.conf")
    call('/etc/rc.d/netif stop wlan0', shell=True)
    call('/etc/rc.d/netif start wlan0', shell=True)
    call('ifconfig wlan0 up', shell=True)


def wificonnection():
    call('/etc/rc.d/netif stop wlan0', shell=True)
    call('/etc/rc.d/netif start wlan0', shell=True)
    call('ifconfig wlan0 up', shell=True)
    # Adding ifconfig wlan0 up because some time it fail.
    call('ifconfig wlan0 up', shell=True)
