#!/usr/local/bin/python3
"""
auto-switch - is used to automatically switch the default interface go down.
"""

import sys
import re
from subprocess import run, PIPE

args = sys.argv
if len(args) != 2:
    sys.exit()
nic = args[1]

NOT_NICS_REGEX = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|" \
                    r"ppp|bridge|wg)[0-9]|vm-[a-z]"

# The default route lines, picked out here rather than through a shell pipe.
DEFAULT_NIC = "\n".join(
    line for line in run(
        ['netstat', '-rn'],
        stdout=PIPE,
        universal_newlines=True,
        check=False
    ).stdout.splitlines()
    if 'default' in line
)

nics = run(
    ['ifconfig', '-l', 'ether'],
    stdout=PIPE,
    universal_newlines=True,
    check=False
)

nics_left_over = nics.stdout.replace(nic, '').strip()
nic_list = sorted(re.sub(NOT_NICS_REGEX, '', nics_left_over).strip().split())

# Stop the script if the nic is not valid or not in the default route.
if re.search(NOT_NICS_REGEX, nic):
    sys.exit(0)
elif nic not in DEFAULT_NIC:
    sys.exit(0)
elif not nic_list:
    sys.exit(0)

nic_ifconfig = run(
    ['ifconfig', nic],
    stdout=PIPE,
    universal_newlines=True,
    check=False
).stdout

dhcp = run(
    ['sysrc', '-n', f'ifconfig_{nic}'],
    stdout=PIPE,
    universal_newlines=True,
    check=False
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
    run(['service', 'netif', 'stop', nic], check=False)
    # Create a marker file for link-up.py to detect runtime state change vs boot.
    # /var/run: root-only, and cleanvar empties it at every boot.
    with open(f'/var/run/link-down-{nic}', 'w', encoding='utf-8') as f:
        f.write('down')
    if dhcp.strip() == 'DHCP':
        for current_nic in nic_list:
            output = run(
                ['ifconfig', current_nic],
                stdout=PIPE,
                universal_newlines=True,
                check=False
            )
            nic_ifconfig = output.stdout
            status_types = [
                'active',
                'associated',
            ]
            found_status = re.search(f"status: ({'|'.join(status_types)})", nic_ifconfig)
            found_inet = re.search(r"inet(\s|6)", nic_ifconfig)
            if found_status and found_inet:
                run(['service', 'dhclient', 'restart', current_nic], check=False)
                break
    else:
        run(['service', 'routing', 'restart'], check=False)
