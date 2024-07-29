#!/usr/local/bin/python3
"""
auto-switch - is used to automatically switches the default interface go down.
"""

import os
import re
import sys
from subprocess import Popen, PIPE

args = sys.argv
if len(args) != 2:
    exit()
nic = args[1]

not_nics_regex = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|wlan" \
                 r"ppp|bridge|wg)[0-9]+(\s*)|vm-[a-z]+(\s*)"

default_nic = Popen(
    'netstat -rn | grep default',
    stdout=PIPE,
    shell=True,
    universal_newlines=True
).stdout.read()

nics = Popen(
    ['ifconfig', '-l', 'ether'],
    stdout=PIPE,
    close_fds=True,
    universal_newlines=True
)

nics_left_over = nics.stdout.read().replace(nic, '').strip()
nic_list = sorted(re.sub(not_nics_regex, '', nics_left_over).strip().split())

# Stop the script if the nic is not valid or not in the default route.
if re.search(not_nics_regex, nic):
    exit(0)
elif nic not in default_nic:
    exit(0)
elif not nic_list:
    exit(0)

nic_ifconfig = Popen(
    ['ifconfig', nic],
    stdout=PIPE,
    close_fds=True,
    universal_newlines=True
).stdout.read()

dhcp = Popen(
    ['sysrc', '-n', f'ifconfig_{nic}'],
    stdout=PIPE,
    close_fds=True,
    universal_newlines=True
).stdout.read()

active_status = (
    'status: active' in nic_ifconfig,
    'status: associated' in nic_ifconfig
)

# Stop the interface if it's not active or associated.
# This removes the interface from the default route.
# Restarting routing adds and nic if there is and other one that is active
# or associated.
if not any(active_status):
    os.system(f'service netif stop {nic}')
    if dhcp.strip() == 'DHCP':
        for current_nic in nic_list:
            output = Popen(
                ['ifconfig', current_nic],
                stdout=PIPE,
                close_fds=True,
                universal_newlines=True
            )
            nic_ifconfig = output.stdout.read()
            status_types = [
                'active',
                'associated',
            ]
            found_status = re.search(f"status: ({'|'.join(status_types)})", nic_ifconfig)
            found_inet = re.search("inet(\s|6)", nic_ifconfig)
            if found_status and found_inet:
                os.system(f'service dhclient restart {current_nic}')
                break
    else:
        os.system('service routing restart')
