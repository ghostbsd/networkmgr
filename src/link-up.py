#!/usr/local/bin/python3

"""devd action for IFNET LINK_UP events on ethernet interfaces.

Invoked by /usr/local/etc/devd/networkmgr.conf with the interface name as its
only argument. Restores DHCP on an interface that auto-switch.py previously
marked as down, or otherwise starts dhclient quietly.
"""

from fnmatch import fnmatchcase
import os
import re
import sys
from subprocess import run, PIPE


def _is_unmanaged(iface):
    """Return True if iface is excluded via rc.conf or /usr/local/etc/networkmgr/unmanaged."""
    patterns = []
    res = run(
        ['sysrc', '-n', 'networkmgr_ignore_interfaces'],
        stdout=PIPE, stderr=PIPE, universal_newlines=True, check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        patterns.extend(t for t in re.split(r'[\s,]+', res.stdout.strip()) if t)
    unmanaged_file = '/usr/local/etc/networkmgr/unmanaged'
    if os.path.isfile(unmanaged_file):
        try:
            with open(unmanaged_file, 'r', encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    entry = line.split('#', 1)[0].strip()
                    if entry:
                        patterns.append(entry)
        except OSError:
            pass
    return any(fnmatchcase(iface, pat) for pat in patterns)

args = sys.argv
if len(args) != 2:
    sys.exit(1)
nic = args[1]

NOT_NICS_REGEX = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|" \
    r"ppp|bridge|wg|wlan)[0-9]+|vm-[a-z]+"

# Stop the script if the nic is not valid or excluded from management.
if re.search(NOT_NICS_REGEX, nic) or _is_unmanaged(nic):
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

rc_nic = re.sub(r'[^A-Za-z0-9_]', '_', nic)
routes_file = f'/usr/local/etc/networkmgr/routes/{rc_nic}.routes'
if os.path.isfile(routes_file):
    try:
        with open(routes_file, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                sline = line.strip()
                if not sline or sline.startswith('#') or '=' not in sline:
                    continue
                k, v = [p.strip() for p in sline.split('=', 1)]
                parts = [p.strip() for p in v.split(',')]
                if k == 'ipv4_route' and len(parts) >= 3:
                    run(
                        ['route', '-n', 'add', '-net', parts[0], parts[2], parts[1]],
                        check=False,
                    )
                elif k == 'ipv6_route' and len(parts) >= 3:
                    run(
                        ['route', '-n', 'add', '-inet6', f'{parts[0]}/{parts[1]}', parts[2]],
                        check=False,
                    )
    except OSError:
        pass
