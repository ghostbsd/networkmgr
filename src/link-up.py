#!/usr/local/bin/python3

"""devd action for IFNET LINK_UP events on ethernet interfaces.

Invoked by /usr/local/etc/devd/networkmgr.conf with the interface name as its
only argument. Restores DHCP on an interface that auto-switch.py previously
marked as down, or otherwise starts dhclient quietly.
"""

import os
import re
import sys
from subprocess import run, PIPE

args = sys.argv
if len(args) != 2:
    sys.exit(1)
nic = args[1]

NOT_NICS_REGEX = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|" \
    r"ppp|bridge|wg|wlan)[0-9]+|vm-[a-z]+"

# Stop the script if the nic is not valid.
if re.search(NOT_NICS_REGEX, nic):
    sys.exit(0)

# This marker file is created by auto-switch.py when the nic is down.
if os.path.exists(f'/var/run/link-down-{nic}'):
    nic_ifconfig = run(
        ['ifconfig', nic],
        stdout=PIPE,
        universal_newlines=True,
        check=False
    ).stdout

    if 'inet ' not in nic_ifconfig:
        run(['service', 'netif', 'start', nic], check=False)

    run(['service', 'routing', 'restart'], check=False)
    run(['service', 'dhclient', 'restart', nic], check=False)
    # Clean up marker file
    os.remove(f'/var/run/link-down-{nic}')
else:
    run(['service', 'dhclient', 'quietstart', nic], check=False)
