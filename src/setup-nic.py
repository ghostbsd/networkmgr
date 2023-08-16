#!/usr/local/bin/python3

import os
import re
import shutil
import sys
from pathlib import Path


def file_content(paths):
    buffers = []
    for path in paths:
        with path.open('r') as file:
            buffers.append(file.read())
    return "".join(buffers)


args = sys.argv
if len(args) != 2:
    exit(1)
nic = args[1]

etc = Path(os.sep, "etc")
rcconf = etc / "rc.conf"
rcconflocal = etc / "rc.conf.local"
wpa_supplicant = etc / "wpa_supplicant.conf"

rcconf_paths = [rcconf]

if rcconflocal.exists():
    rcconf_paths.append(rcconflocal)

rcconf_content = file_content(rcconf_paths)

notnics_regex = "(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|" \
    "ppp|bridge|wg|wlan)[0-9]+|vm-[a-z]+"

# wifi_driver_regex is taken from devd.conf wifi-driver-regex
wifi_driver_regex = "(ath|bwi|bwn|ipw|iwlwifi|iwi|iwm|iwn|malo|mwl|otus|" \
    "ral|rsu|rtw|rtwn|rum|run|uath|upgt|ural|urtw|wpi|wtap|zyd)[0-9]+"

if re.search(notnics_regex, nic):
    exit(0)

if re.search(wifi_driver_regex, nic):
    if not wpa_supplicant.exists():
        wpa_supplicant.touch()
        shutil.chown(wpa_supplicant, user="root", group="wheel")
        wpa_supplicant.chmod(0o765)
    for wlanNum in range(0, 9):
        if f'wlan{wlanNum}' not in rcconf_content:
            break
    if f'wlans_{nic}=' not in rcconf_content:
        with rcconf.open('a') as rc:
            rc.writelines(f'wlans_{nic}="wlan{wlanNum}"\n')
            rc.writelines(f'ifconfig_wlan{wlanNum}="WPA DHCP"\n')
else:
    if f'ifconfig_{nic}=' not in rcconf_content:
        with rcconf.open('a') as rc:
            rc.writelines(f'ifconfig_{nic}="DHCP"\n')
os.system(f'/etc/pccard_ether {nic} startchildren')
