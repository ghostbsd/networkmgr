#!/usr/local/bin/python3

import sys
import os
import re
from subprocess import Popen, PIPE

args = sys.argv
if len(args) != 2:
    exit()
nic = args[1]

cmd = ["kenv", "-q", "rc_system"]
rc_system = Popen(cmd, stdout=PIPE, universal_newlines=True).stdout.read()
openrc = True if 'openrc' in rc_system else False

cmd = 'netstat -rn | grep default'
defautl_nic = Popen(cmd, stdout=PIPE, shell=True, universal_newlines=True).stdout.read()

nic_ifconfig = Popen(
    ['ifconfig', nic],
    stdout=PIPE,
    close_fds=True,
    universal_newlines=True
).stdout.read()

# Only stop dhclient if the status is not active or associated
active_status = (
    'status: active' in nic_ifconfig,
    'status: associated' in nic_ifconfig
)
if any(active_status) is False:
    if openrc:
        os.system(f'service dhcpcd.{nic} stop')
    else:
        if 'wlan' in nic:
            os.system(f'service dhclient stop {nic}')
        else:
            os.system(f'service netif stop {nic}')
            os.system('service routing restart')

nics = Popen(
    ['ifconfig', '-l', 'ether'],
    stdout=PIPE,
    close_fds=True,
    universal_newlines=True
)

notnics_regex = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|" \
    r"ppp|bridge|wg)[0-9]+(\s*)|vm-[a-z]+(\s*)"

nics_lelfover = nics.stdout.read().replace(nic, '').strip()
nic_list = sorted(re.sub(notnics_regex, '', nics_lelfover).strip().split())

if not nic_list:
    exit()

for current_nic in nic_list:
    output = Popen(
        ['ifconfig', current_nic],
        stdout=PIPE,
        close_fds=True,
        universal_newlines=True
    )
    nic_ifconfig = output.stdout.read()
    if 'status: active' in nic_ifconfig or 'status: associated' in nic_ifconfig:
        if 'inet ' in nic_ifconfig or 'inet6' in nic_ifconfig:
            if openrc:
                os.system(f'service dhcpcd.{current_nic} restart')
            else:
                os.system(f'service dhclient restart {current_nic}')
            break
