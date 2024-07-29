#!/usr/bin/env python

import os
import re
from subprocess import check_output


def get_interface_settings(active_nic):
    interface_settings = {}
    rc_conf = open("/etc/rc.conf", "r").read()
    dhcp_search = re.findall(fr'^ifconfig_{active_nic}=".*DHCP', rc_conf, re.MULTILINE)
    print(f"dhcp_search is {dhcp_search} and the length is {len(dhcp_search)}")
    if len(dhcp_search) < 1:
        dhcp_status_output = "Manual"
    else:
        dhcp_status_output = "DHCP"

    ip_regex = r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+'

    ifcmd = f"ifconfig -f inet:dotted {active_nic}"
    ifoutput = check_output(ifcmd.split(" "), universal_newlines=True)
    re_ip = re.search(fr'inet {ip_regex}', ifoutput)
    if re_ip:
        if_ip = re_ip.group().replace("inet ", "").strip()
        re_netmask = re.search(fr'netmask {ip_regex}', ifoutput)
        if_netmask = re_netmask.group().replace("netmask ", "").strip()
        re_broadcast = re.search(fr'broadcast {ip_regex}', ifoutput)
        if_broadcast = re_broadcast.group().replace("broadcast ", "").strip()
    else:
        if_ip = ""
        if_netmask = ""
        if_broadcast = ""
    if dhcp_status_output == "DHCP":
        dhclient_leases = f"/var/db/dhclient.leases.{active_nic}"

        if os.path.exists(dhclient_leases) is False:
            print(f"DHCP is enabled, but we're unable to read the lease file at /var/db/dhclient.leases.{active_nic}")
            gateway = ""
        else:
            dh_lease = open(dhclient_leases, "r").read()
            re_gateway = re.search(fr"option routers {ip_regex}", dh_lease)
            gateway = re_gateway.group().replace("option routers ", "")
    else:
        rc_conf = open('/etc/rc.conf', 'r').read()
        re_gateway = re.search(fr'^defaultrouter="{ip_regex}"', rc_conf, re.MULTILINE)
        if re_gateway:
            gateway = re_gateway.group().replace('"', "")
            gateway = gateway.replace('defaultrouter=', "")
        else:
            gateway = ""

    if os.path.exists('/etc/resolv.conf'):
        resolv_conf = open('/etc/resolv.conf').read()
        nameservers = re.findall(fr'^nameserver {ip_regex}', str(resolv_conf), re.MULTILINE)
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
    interface_settings["Assignment Method"] = dhcp_status_output
    interface_settings["Interface IP"] = if_ip
    interface_settings["Interface Subnet Mask"] = if_netmask
    interface_settings["Broadcast Address"] = if_broadcast
    interface_settings["Default Gateway"] = gateway
    interface_settings["Search Domain"] = domain_search

    for num in range(len(nameservers)):
        interface_settings[
            f"DNS Server {num + 1}"
        ] = str(nameservers[num]).replace("nameserver", "").strip()
    # if DNS Server 1 and 2 are missing create them with empty string
    if "DNS Server 1" not in interface_settings:
        interface_settings["DNS Server 1"] = ""
    if "DNS Server 2" not in interface_settings:
        interface_settings["DNS Server 2"] = ""

    return interface_settings
