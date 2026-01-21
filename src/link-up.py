#!/usr/local/bin/python3

import os
import re
import sys
from subprocess import run, PIPE

args = sys.argv
if len(args) != 2:
    exit(1)
nic = args[1]

not_nics_regex = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|" \
    r"ppp|bridge|wg|wlan)[0-9]+|vm-[a-z]+"

# Stop the script if the nic is not valid.
if re.search(not_nics_regex, nic):
    exit(0)

# This marker file is created by auto-switch.py when the nic is down.
if os.path.exists(f'/tmp/link-down-{nic}'):
    nic_ifconfig = run(
        ['ifconfig', nic],
        stdout=PIPE,
        universal_newlines=True
    ).stdout

    if 'inet ' not in nic_ifconfig:
        run(['service', 'netif', 'start', nic])

    run(['service', 'routing', 'restart'])
    run(['service', 'dhclient', 'restart', nic])
    # Clean up marker file
    os.remove(f'/tmp/link-down-{nic}')
else:
    run(['service', 'dhclient', 'quietstart', nic])
