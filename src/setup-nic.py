#!/usr/local/bin/python3

import os
import re
import shutil
import sys
from pathlib import Path
from subprocess import run


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
rc_conf = etc / "rc.conf"
rc_conf_local = etc / "rc.conf.local"
wpa_supplicant = etc / "wpa_supplicant.conf"

rc_conf_paths = [rc_conf]

if rc_conf_local.exists():
    rc_conf_paths.append(rc_conf_local)

rc_conf_content = file_content(rc_conf_paths)

not_nics_regex = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|" \
    r"ppp|bridge|wg|wlan)[0-9]+|vm-[a-z]+"

# wifi_driver_regex is taken from devd.conf wifi-driver-regex
wifi_driver_regex = "(ath|ath[0-9]+k|bwi|bwn|ipw|iwlwifi|iwi|iwm|iwn|malo|mwl|mt79|otus|" \
    "ral|rsu|rtw|rtwn|rum|run|uath|upgt|ural|urtw|wpi|wtap|zyd)[0-9]+"

if re.search(not_nics_regex, nic):
    exit(0)

if re.search(wifi_driver_regex, nic):
    if not wpa_supplicant.exists():
        wpa_supplicant.touch()
        shutil.chown(wpa_supplicant, user="root", group="wheel")
        wpa_supplicant.chmod(0o600)  # Secure: root-only, contains passwords
    if f'wlans_{nic}=' not in rc_conf_content:
        for wlanNum in range(9):
            if f'wlan{wlanNum}' not in rc_conf_content:
                run(['sysrc', f'wlans_{nic}="wlan{wlanNum}"'])
                run(['sysrc', f'ifconfig_wlan{wlanNum}="WPA DHCP"'])
                break
    run(['/etc/pccard_ether', nic, 'startchildren'])
else:
    if f'ifconfig_{nic}=' not in rc_conf_content:
        run(['sysrc', f'ifconfig_{nic}=DHCP'])
    run(['/etc/pccard_ether', nic, 'start'])
