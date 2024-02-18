#!/usr/local/bin/python3
"""
auto-switch - is used to automatically switches the default interface go down.
"""

import sys
import os
import re
from subprocess import Popen, PIPE

args = sys.argv
if len(args) != 2:
    exit()
nic = args[1]

not_nics_regex = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|wlan" \
                    r"ppp|bridge|wg)[0-9]+(\s*)|vm-[a-z]+(\s*)"

default_nic = Popen(
    'netstat -rn | grep default',
    shell=True,
    universal_newlines=True
).stdout.read()

# Stop the script if the nic is not valid or not in the default route.
if re.search(not_nics_regex, nic):
    exit(0)
elif nic not in default_nic:
    exit(0)

nic_ifconfig = Popen(
    ['ifconfig', nic],
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
    os.system('service routing restart')
