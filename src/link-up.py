#!/usr/local/bin/python3

import os
import re
import sys
from subprocess import Popen, PIPE

args = sys.argv
if len(args) != 2:
    exit(1)
nic = args[1]

not_nics_regex = "(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|" \
    "ppp|bridge|wg|wlan)[0-9]+|vm-[a-z]+"

# Stop the script if the nic is not valid.
if re.search(not_nics_regex, nic):
    exit(0)

dhcp = Popen(
    ['sysrc', '-n', f'ifconfig_{nic}'],
    stdout=PIPE,
    close_fds=True,
    universal_newlines=True
).stdout.read()

if os.path.exists(f'/tmp/network-{nic}'):
    network = open(f'/tmp/network-{nic}', 'r').read()
    if 'attached' in network:
        if dhcp.strip() == 'DHCP':
            Popen(f'service dhclient quietstart {nic}', shell=True)
        else:
            Popen(f'service routing restart', shell=True)
        with open(f'/tmp/network-{nic}', 'w') as network:
            network.writelines(f'linked')
        exit(0)

nic_ifconfig = Popen(
    ['ifconfig', nic],
    stdout=PIPE,
    close_fds=True,
    universal_newlines=True
).stdout.read()

if 'inet ' in nic_ifconfig:
    Popen(
        f'service routing restart ; '
        f'service dhclient restart {nic}',
        shell=True
    )
else:
    Popen(
        f'service netif start {nic} ; '
        'sleep 1 ; '
        f'service routing restart ; '
        f'service dhclient restart {nic}',
        shell=True
    )
