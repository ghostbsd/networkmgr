#!/usr/local/bin/python3
"""
auto-switch - is used to automatically switch the default interface go down.
"""

import sys
import re
from subprocess import run, PIPE

args = sys.argv
if len(args) != 2:
    exit()
nic = args[1]

not_nics_regex = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|" \
                    r"ppp|bridge|wg)[0-9]|vm-[a-z]"

default_nic = run(
    'netstat -rn | grep default',
    stdout=PIPE,
    shell=True,
    universal_newlines=True
).stdout

nics = run(
    ['ifconfig', '-l', 'ether'],
    stdout=PIPE,
    universal_newlines=True
)

nics_left_over = nics.stdout.replace(nic, '').strip()
nic_list = sorted(re.sub(not_nics_regex, '', nics_left_over).strip().split())

# Stop the script if the nic is not valid or not in the default route.
if re.search(not_nics_regex, nic):
    exit(0)
elif nic not in default_nic:
    exit(0)
elif not nic_list:
    exit(0)

nic_ifconfig = run(
    ['ifconfig', nic],
    stdout=PIPE,
    universal_newlines=True
).stdout

dhcp = run(
    ['sysrc', '-n', f'ifconfig_{nic}'],
    stdout=PIPE,
    universal_newlines=True
).stdout

active_status = (
    'status: active' in nic_ifconfig,
    'status: associated' in nic_ifconfig
)

# Stop the interface if it's not active or associated.
# This removes the interface from the default route.
# Restarting routing adds and nic if there is another one that is active
# or associated.
if not any(active_status):
    run(['service', 'netif', 'stop', nic])
    # Create a marker file for link-up.py to detect runtime state change vs boot
    with open(f'/tmp/link-down-{nic}', 'w') as f:
        f.write('down')
    if dhcp.strip() == 'DHCP':
        for current_nic in nic_list:
            output = run(
                ['ifconfig', current_nic],
                stdout=PIPE,
                universal_newlines=True
            )
            nic_ifconfig = output.stdout
            status_types = [
                'active',
                'associated',
            ]
            found_status = re.search(f"status: ({'|'.join(status_types)})", nic_ifconfig)
            found_inet = re.search(r"inet(\s|6)", nic_ifconfig)
            if found_status and found_inet:
                run(['service', 'dhclient', 'restart', current_nic])
                break
    else:
        run(['service', 'routing', 'restart'])
