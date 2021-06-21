#!/usr/bin/env python3

import os
import re
import sys

args = sys.argv
if len(args) != 2:
    exit(1)
nic = args[1]

rcconf = open('/etc/rc.conf', 'r').read()
if os.path.exists('/etc/rc.conf.local'):
    rcconflocal = open('/etc/rc.conf.local', 'r').read()
else:
    rcconflocal = "None"

notnics_regex = "(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|" \
    "ppp|bridge|ixautomation|vm-ixautomation|wg|wlan)[0-9]+"

# wifi_driver_regex is taken from devd.conf wifi-driver-regex
wifi_driver_regex = "(ath|bwi|bwn|ipw|iwi|iwm|iwn|malo|mwl|otus|ral|rsu|" \
    "rtwn|rum|run|uath|upgt|ural|urtw|wi|wpi|wtap|zyd)[0-9]+"

if re.search(notnics_regex, nic):
    exit(0)
if re.search(wifi_driver_regex, nic):
    if not os.path.exists('/etc/wpa_supplicant.conf'):
        open('/etc/wpa_supplicant.conf', 'a').close()
        os.system('chown root:wheel /etc/wpa_supplicant.conf')
        os.system('chmod 765 /etc/wpa_supplicant.conf')
    for wlanNum in range(0, 9):
        if f'wlan{wlanNum}' not in (rcconf + rcconflocal):
            break
    if f'wlans_{nic}=' not in (rcconf + rcconflocal):
        rc = open('/etc/rc.conf', 'a')
        rc.writelines(f'wlans_{nic}="wlan{wlanNum}"\n')
        rc.writelines(f'ifconfig_wlan{wlanNum}="WPA DHCP"\n')
        rc.close()
else:
    if f'ifconfig_{nic}=' not in (rcconf + rcconflocal):
        rc = open('/etc/rc.conf', 'a')
        rc.writelines(f'ifconfig_{nic}="DHCP"\n')
        rc.close()
os.system(f'/etc/pccard_ether {nic} startchildren')
