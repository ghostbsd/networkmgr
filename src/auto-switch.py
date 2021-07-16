#!/usr/bin/env python3

import sys
import os
from subprocess import Popen, PIPE

args = sys.argv
if len(args) != 2:
    exit()
nic = args[1]

cmd = ["kenv", "rc_system"]
rc_system = Popen(cmd, stdout=PIPE, universal_newlines=True).stdout.read()
openrc = True if 'openrc' in rc_system else False

cmd = 'netstat -rn | grep default'
defautl_nic = Popen(cmd, stdout=PIPE, shell=True, universal_newlines=True).stdout.read()

if openrc:
    os.system(f'service dhcpcd.{nic} stop')
else:
    if nic in defautl_nic and 'wlan' not in defautl_nic:
        os.system(f'service netif stop {nic}')

nics = Popen(
    ['ifconfig', '-l', 'ether'],
    stdout=PIPE,
    close_fds=True,
    universal_newlines=True
)

nics = nics.stdout.read().replace(nic, '').strip()

if not nics:
    exit()

nic_list = nics.split()

for nics in nic_list:
    output = Popen(
        ['ifconfig', nics],
        stdout=PIPE,
        close_fds=True,
        universal_newlines=True
    )
    nic_ifconfig = output.stdout.read()
    if 'status: active' in nic_ifconfig or 'status: associated' in nic_ifconfig:
        if 'inet ' in nic_ifconfig or 'inet6' in nic_ifconfig:
            if openrc:
                os.system(f'service dhcpcd.{nics} restart')
            else:
                os.system(f'service dhclient restart {nics}')
            break
