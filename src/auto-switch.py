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
openrc = 'openrc' in rc_system

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
if not any(active_status):
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
    status_types = [
        'active',
        'associated',
    ]
    found_status = re.search(f"status: ({'|'.join(status_types)})", nic_ifconfig)
    found_inet = re.search("inet(\s|6)", nic_ifconfig)
    if found_status and found_inet:
        if openrc:
            os.system(f'service dhcpcd.{current_nic} restart')
        else:
            os.system(f'service dhclient restart {current_nic}')
        break
