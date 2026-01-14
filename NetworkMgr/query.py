#!/usr/bin/env python

from subprocess import check_output
import re
import os


def get_interface_settings_ipv6(active_nic):
    """Get IPv6 settings for the given network interface."""
    ipv6_settings = {}
    rc_conf = open("/etc/rc.conf", "r").read()

    # Check if SLAAC is enabled (accept_rtadv in rc.conf)
    slaac_search = re.search(
        fr'^ifconfig_{active_nic}_ipv6=".*accept_rtadv',
        rc_conf,
        re.MULTILINE | re.IGNORECASE
    )
    if slaac_search:
        ipv6_settings["Assignment Method"] = "SLAAC"
    else:
        # Check for static IPv6 configuration
        static_search = re.search(
            fr'^ifconfig_{active_nic}_ipv6="inet6\s+([0-9a-fA-F:]+).*prefixlen\s+(\d+)',
            rc_conf,
            re.MULTILINE
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
    except Exception:
        ipv6_settings["Interface IPv6"] = ""
        ipv6_settings["Prefix Length"] = "64"

    # Get IPv6 default gateway from rc.conf or routing table
    # Pattern allows optional interface suffix for link-local (e.g., fe80::1%em0)
    gateway_search = re.search(
        r'^ipv6_defaultrouter="([0-9a-fA-F:%]+)"',
        rc_conf,
        re.MULTILINE
    )
    if gateway_search:
        ipv6_settings["Default Gateway"] = gateway_search.group(1)
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
        except Exception:
            ipv6_settings["Default Gateway"] = ""

    # Get IPv6 DNS servers from resolv.conf
    ipv6_settings["DNS Server 1"] = ""
    if os.path.exists('/etc/resolv.conf'):
        resolv_conf = open('/etc/resolv.conf').read()
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
        resolv_conf = open('/etc/resolv.conf').read()
        search_match = re.search(r'^search\s+(.+)$', resolv_conf, re.MULTILINE)
        if search_match:
            ipv6_settings["Search Domain"] = search_match.group(1).strip()
        else:
            domain_match = re.search(r'^domain\s+(.+)$', resolv_conf, re.MULTILINE)
            if domain_match:
                ipv6_settings["Search Domain"] = domain_match.group(1).strip()

    return ipv6_settings


def get_interface_settings(active_nic):
    interface_settings = {}
    rc_conf = open("/etc/rc.conf", "r").read()
    DHCPSearch = re.findall(fr'^ifconfig_{active_nic}=".*DHCP', rc_conf, re.MULTILINE)
    print(f"DHCPSearch is {DHCPSearch} and the length is {len(DHCPSearch)}")
    if len(DHCPSearch) < 1:
        DHCPStatusOutput = "Manual"
    else:
        DHCPStatusOutput = "DHCP"

    IPREGEX = r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+'

    ifcmd = f"ifconfig -f inet:dotted {active_nic}"
    ifoutput = check_output(ifcmd.split(" "), universal_newlines=True)
    re_ip = re.search(fr'inet {IPREGEX}', ifoutput)
    if re_ip:
        if_ip = re_ip.group().replace("inet ", "").strip()
        re_netmask = re.search(fr'netmask {IPREGEX}', ifoutput)
        if_netmask = re_netmask.group().replace("netmask ", "").strip()
        re_broadcast = re.search(fr'broadcast {IPREGEX}', ifoutput)
        if_broadcast = re_broadcast.group().replace("broadcast ", "").strip()
    else:
        if_ip = ""
        if_netmask = ""
        if_broadcast = ""
    if (DHCPStatusOutput == "DHCP"):
        dhclient_leases = f"/var/db/dhclient.leases.{active_nic}"

        if os.path.exists(dhclient_leases) is False:
            print("DHCP is enabled, but we're unable to read the lease "
                  f"file a /var/db/dhclient.leases.{active_nic}")
            gateway = ""
        else:
            dh_lease = open(dhclient_leases, "r").read()
            re_gateway = re.search(fr"option routers {IPREGEX}", dh_lease)
            gateway = re_gateway.group().replace("option routers ", "")
    else:
        rc_conf = open('/etc/rc.conf', 'r').read()
        re_gateway = re.search(fr'^defaultrouter="{IPREGEX}"', rc_conf, re.MULTILINE)
        if re_gateway:
            gateway = re_gateway.group().replace('"', "")
            gateway = gateway.replace('defaultrouter=', "")
        else:
            gateway = ""

    if os.path.exists('/etc/resolv.conf'):
        resolv_conf = open('/etc/resolv.conf').read()
        nameservers = re.findall(fr'^nameserver {IPREGEX}', str(resolv_conf), re.MULTILINE)
        print(nameservers)

        re_domain_search = re.findall('search [a-zA-Z.]*', str(resolv_conf))
        if len(re_domain_search) < 1:
            re_domain_search = re.findall('domain (.*)', resolv_conf)
        domain_search = str(re_domain_search).replace("domain ", "")
        domain_search = domain_search.replace("'", "")
        domain_search = domain_search.replace("[", "")
        domain_search = domain_search.replace("]", "")
        domain_search = domain_search.replace('search', '').strip()
    else:
        domain_search = ''
        nameservers = []

    interface_settings["Active Interface"] = active_nic
    interface_settings["Assignment Method"] = DHCPStatusOutput
    interface_settings["Interface IP"] = if_ip
    interface_settings["Interface Subnet Mask"] = if_netmask
    interface_settings["Broadcast Address"] = if_broadcast
    interface_settings["Default Gateway"] = gateway
    interface_settings["Search Domain"] = domain_search

    for num in range(len(nameservers)):
        interface_settings[
            f"DNS Server {num + 1}"
        ] = str(nameservers[(num)]).replace("nameserver", "").strip()
    # if DNS Server 1 and 2 are missing create them with empty string
    if "DNS Server 1" not in interface_settings:
        interface_settings["DNS Server 1"] = ""
    if "DNS Server 2" not in interface_settings:
        interface_settings["DNS Server 2"] = ""

    return interface_settings
