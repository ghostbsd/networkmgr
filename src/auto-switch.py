#!/usr/bin/env python3

import sys
import os
import re
from subprocess import Popen, PIPE

args = sys.argv
if len(args) != 2:
    exit()
nic = args[1]

cmd = ["kenv", "rc_system"]
rc_system = Popen(cmd, stdout=PIPE, universal_newlines=True).stdout.read()
openrc = True if 'openrc' in rc_system else False

if openrc:
    os.system(f'service dhcpcd.{nic} stop')

nics = Popen(
    ['ifconfig', '-l'],
    stdout=PIPE,
    close_fds=True,
    universal_newlines=True
)
nics = nics.stdout.read().strip()

notnics_regex = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|" \
    r"ppp|bridge|ixautomation|vm-ixautomation|wg)[0-9]+(\s*)"

recompile = re.compile(notnics_regex)
nics = recompile.sub('', nics).replace(nic, '').strip().

if not nics:
    exit()

nic_list = nics.split()

for card in nic_list:
    print(card)
    ncard = 'ifconfig -l'
    output = Popen(
        ['ifconfig', card],
        stdout=PIPE,
        close_fds=True,
        universal_newlines=True
    )
    nic_ifconfig = output.stdout.read()
    if 'status: active' in nic_ifconfig or 'status: associated' in nic_ifconfig:
        if 'inet ' in nic_ifconfig or 'inet6' in nic_ifconfig:
            if openrc:
                os.system(f'service dhcpcd.{card} restart')
            else:
                os.system(f'service dhclient restart {card}')
            break
