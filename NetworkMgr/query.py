#!/usr/bin/env python

"""Read-only queries for the current network configuration.

Answers what the configuration UI needs to know about an interface: its
assignment method, addresses, gateway, DNS servers and search domain, for
both IPv4 and IPv6. Values come from rc.conf(5) via sysrc, from ifconfig,
from the routing table and from /etc/resolv.conf.
"""

from subprocess import CalledProcessError, check_output, run
import re
import os

IP_REGEX = r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+'


def _rc_conf_value(name):
    """Return the effective value of an rc.conf(5) variable.

    sysrc reads every file in rc_conf_files, so a setting placed in
    /etc/rc.conf.local is seen here and overrides /etc/rc.conf, matching
    both the boot-time behaviour and where our own sysrc writes land.

    Args:
        name (str): The rc.conf variable to read, such as "defaultrouter".

    Returns:
        str: The variable's value with surrounding whitespace removed, or an
        empty string if it is set nowhere.
    """
    sysrc = run(
        ['sysrc', '-n', name],
        capture_output=True,
        universal_newlines=True,
        check=False
    )
    if sysrc.returncode != 0:
        return ""
    return sysrc.stdout.strip()


def _address_after(keyword, text):
    """Read the dotted-quad address that follows a keyword.

    Args:
        keyword (str): the word before the address, such as "netmask".
        text (str): ifconfig output.

    Returns:
        str: the address, or an empty string when the keyword is not there.
        A missing field is ordinary rather than exceptional: a loopback or
        point-to-point interface carries an address with no broadcast.
    """
    found = re.search(fr'{keyword} {IP_REGEX}', text)
    if not found:
        return ""
    return found.group().replace(f'{keyword} ', '').strip()


def get_interface_settings_ipv6(active_nic):
    """Collect the IPv6 settings of one network interface.

    Args:
        active_nic (str): Interface name, such as "em0" or "wlan0".

    Returns:
        dict[str, str]: Assignment Method, Interface IPv6, Prefix Length,
        Default Gateway, DNS Server 1 and Search Domain. Missing values are
        empty strings rather than absent keys.
    """
    ipv6_settings = {}
    ifconfig_ipv6 = _rc_conf_value(f'ifconfig_{active_nic}_ipv6')

    # Check if SLAAC is enabled (accept_rtadv in rc.conf)
    slaac_search = re.search(
        r'accept_rtadv',
        ifconfig_ipv6,
        re.IGNORECASE
    )
    if slaac_search:
        ipv6_settings["Assignment Method"] = "SLAAC"
    else:
        # Check for static IPv6 configuration
        static_search = re.search(
            r'^inet6\s+([0-9a-fA-F:]+).*prefixlen\s+(\d+)',
            ifconfig_ipv6
        )
        if static_search:
            ipv6_settings["Assignment Method"] = "Manual"
        else:
            ipv6_settings["Assignment Method"] = "SLAAC"  # Default

    # Get current IPv6 address from ifconfig
    try:
        ifcmd = f"ifconfig {active_nic}"
        ifoutput = check_output(ifcmd.split(" "), universal_newlines=True)

        # Find global IPv6 addresses (exclude link-local fe80::)
        ipv6_matches = re.findall(
            r'inet6 ([0-9a-fA-F:]+)%?\S* prefixlen (\d+)',
            ifoutput
        )
        # Filter out link-local addresses
        global_addrs = [(addr, plen) for addr, plen in ipv6_matches
                        if not addr.lower().startswith('fe80:')]

        if global_addrs:
            ipv6_settings["Interface IPv6"] = global_addrs[0][0]
            ipv6_settings["Prefix Length"] = global_addrs[0][1]
        else:
            ipv6_settings["Interface IPv6"] = ""
            ipv6_settings["Prefix Length"] = "64"
    except (CalledProcessError, OSError):
        ipv6_settings["Interface IPv6"] = ""
        ipv6_settings["Prefix Length"] = "64"

    # The suffix allows a link-local gateway (fe80::1%em0). An unset
    # variable reads as the "NO" sentinel, which fails this match.
    gateway_search = re.fullmatch(
        r'[0-9a-fA-F:]+(?:%[a-zA-Z0-9]+)?',
        _rc_conf_value('ipv6_defaultrouter')
    )
    if gateway_search:
        ipv6_settings["Default Gateway"] = gateway_search.group()
    else:
        # Try to get from routing table
        try:
            netstat_output = check_output(
                'netstat -rn -f inet6'.split(),
                universal_newlines=True
            )
            for line in netstat_output.splitlines():
                if line.startswith('default'):
                    parts = line.split()
                    if len(parts) >= 2:
                        # Remove interface suffix if present (e.g., fe80::1%em0)
                        gw = parts[1].split('%')[0]
                        ipv6_settings["Default Gateway"] = gw
                        break
            else:
                ipv6_settings["Default Gateway"] = ""
        except (CalledProcessError, OSError):
            ipv6_settings["Default Gateway"] = ""

    # Get IPv6 DNS servers from resolv.conf
    ipv6_settings["DNS Server 1"] = ""
    if os.path.exists('/etc/resolv.conf'):
        with open('/etc/resolv.conf', encoding='utf-8') as resolv_file:
            resolv_conf = resolv_file.read()
        # Match IPv6 nameservers (must contain at least one colon)
        ipv6_nameservers = re.findall(
            r'^nameserver\s+([0-9a-fA-F]*:[0-9a-fA-F:]+)',
            resolv_conf,
            re.MULTILINE
        )
        if ipv6_nameservers:
            ipv6_settings["DNS Server 1"] = ipv6_nameservers[0]

    # Get search domain (shared with IPv4)
    ipv6_settings["Search Domain"] = ""
    if os.path.exists('/etc/resolv.conf'):
        with open('/etc/resolv.conf', encoding='utf-8') as resolv_file:
            resolv_conf = resolv_file.read()
        search_match = re.search(r'^search\s+(.+)$', resolv_conf, re.MULTILINE)
        if search_match:
            ipv6_settings["Search Domain"] = search_match.group(1).strip()
        else:
            domain_match = re.search(r'^domain\s+(.+)$', resolv_conf, re.MULTILINE)
            if domain_match:
                ipv6_settings["Search Domain"] = domain_match.group(1).strip()

    return ipv6_settings


def get_interface_settings(active_nic):
    """Collect the IPv4 settings of one network interface.

    Args:
        active_nic (str): Interface name, such as "em0" or "wlan0".

    Returns:
        dict[str, str]: Active Interface, Assignment Method, Interface IP,
        Interface Subnet Mask, Broadcast Address, Default Gateway, Search
        Domain and one "DNS Server N" entry per nameserver. DNS Server 1 and
        2 are always present, empty when unset.
    """
    interface_settings = {}
    if 'DHCP' in _rc_conf_value(f'ifconfig_{active_nic}'):
        dhcp_status_output = "DHCP"
    else:
        dhcp_status_output = "Manual"

    ifcmd = f"ifconfig -f inet:dotted {active_nic}"
    ifoutput = check_output(ifcmd.split(" "), universal_newlines=True)
    if_ip = _address_after('inet', ifoutput)
    if_netmask = _address_after('netmask', ifoutput)
    if_broadcast = _address_after('broadcast', ifoutput)
    if dhcp_status_output == "DHCP":
        dhclient_leases = f"/var/db/dhclient.leases.{active_nic}"

        if os.path.exists(dhclient_leases) is False:
            # No lease file yet, so there is no router option to read. The
            # window shows an empty gateway rather than a stale one.
            gateway = ""
        else:
            with open(dhclient_leases, "r", encoding='utf-8') as lease_file:
                dh_lease = lease_file.read()
            # dhclient appends leases, so the last one is the current one.
            routers = re.findall(fr'option routers ({IP_REGEX})', dh_lease)
            gateway = routers[-1] if routers else ""
    else:
        # An unset defaultrouter reads as the "NO" sentinel from
        # /etc/defaults/rc.conf, which fails this match.
        re_gateway = re.fullmatch(IP_REGEX, _rc_conf_value('defaultrouter'))
        if re_gateway:
            gateway = re_gateway.group()
        else:
            gateway = ""

    if os.path.exists('/etc/resolv.conf'):
        with open('/etc/resolv.conf', encoding='utf-8') as resolv_file:
            resolv_conf = resolv_file.read()
        nameservers = re.findall(fr'^nameserver {IP_REGEX}', str(resolv_conf), re.MULTILINE)

        domain_search = ''
        search_match = re.search(r'^search\s+(.+)$', resolv_conf, re.MULTILINE)
        if search_match:
            domain_search = search_match.group(1).strip()
        else:
            domain_match = re.search(r'^domain\s+(.+)$', resolv_conf, re.MULTILINE)
            if domain_match:
                domain_search = domain_match.group(1).strip()
    else:
        domain_search = ''
        nameservers = []

    interface_settings["Active Interface"] = active_nic
    interface_settings["Assignment Method"] = dhcp_status_output
    interface_settings["Interface IP"] = if_ip
    interface_settings["Interface Subnet Mask"] = if_netmask
    interface_settings["Broadcast Address"] = if_broadcast
    interface_settings["Default Gateway"] = gateway
    interface_settings["Search Domain"] = domain_search

    for num, nameserver in enumerate(nameservers):
        interface_settings[
            f"DNS Server {num + 1}"
        ] = str(nameserver).replace("nameserver", "").strip()
    # if DNS Server 1 and 2 are missing create them with empty string
    if "DNS Server 1" not in interface_settings:
        interface_settings["DNS Server 1"] = ""
    if "DNS Server 2" not in interface_settings:
        interface_settings["DNS Server 2"] = ""

    return interface_settings
