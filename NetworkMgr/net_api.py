#!/usr/bin/env python

import re
from subprocess import Popen, PIPE, run, check_output
from time import sleep


def card_online(net_card):
    lan = Popen('ifconfig ' + net_card, shell=True, stdout=PIPE, universal_newlines=True)
    return 'inet ' in lan.stdout.read()


def default_card():
    cmd = "netstat -rn | grep default"
    nics = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    device = nics.stdout.readlines()
    if len(device) == 0:
        return None
    else:
        return list(filter(None, device[0].rstrip().split()))[3]


def if_wlan_disable(wifi_card):
    cmd = "ifconfig %s list scan" % wifi_card
    nics = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    return not nics.stdout.read()


def if_statue(wifi_card):
    cmd = "ifconfig %s" % wifi_card
    wl = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    wlout = wl.stdout.read()
    return "associated" in wlout


def get_ssid(wifi_card):
    wlan = Popen('ifconfig %s | grep ssid' % wifi_card, shell=True, stdout=PIPE, universal_newlines=True)
    # If there are quotation marks in the string, use that as a separator,
    # otherwise use the default whitespace. This is to handle ssid strings
    # with spaces in them. These ssid strings will be double-quoted by ifconfig
    temp = wlan.stdout.readlines()[0].rstrip()
    if '"' in temp:
        out = temp.split('"')[1]
    else:
        out = temp.split()[1]
    return out


def nics_list():
    not_nics_regex = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|" \
        r"faith|ppp|bridge|wg)[0-9]+(\s*)|vm-[a-z]+(\s*)"
    nics = Popen(
        'ifconfig -l',
        shell=True,
        stdout=PIPE,
        universal_newlines=True
    ).stdout.read().strip()
    return sorted(re.sub(not_nics_regex, '', nics).strip().split())


def if_card_connected(net_card):
    wifi = Popen('ifconfig ' + net_card, shell=True, stdout=PIPE, universal_newlines=True)
    return 'status: active' in wifi.stdout.read()


def calculate_signal_strength_percentage(signal):
    sig = int(signal.partition(':')[0])
    noise = int(signal.partition(':')[2])
    return int((sig - noise) * 4)


def network_service_state():
    return False


def network_dictionary():
    nlist = nics_list()
    main_dictionary = {
        'service': network_service_state(),
        'default': default_card()
    }
    cards = {}
    for card in nlist:
        if 'wlan' in card:
            scanv = f"ifconfig {card} list scan | grep -va BSSID"
            wifi = Popen(scanv, shell=True, stdout=PIPE, universal_newlines=True)
            connection_info = {}
            for line in wifi.stdout:
                # don't sort empty ssid
                # Window, macOS and Linux does not show does
                if line.startswith(" " * 5):
                    continue
                ssid = line[:33].strip()
                info = line[:83][33:].strip().split()
                percentage = calculate_signal_strength_percentage(info[3])
                # if ssid exist and percentage is higher keep it
                # else add the new one if percentage is higher
                if ssid in connection_info:
                    if connection_info[ssid][4] > percentage:
                        continue
                info[3] = percentage
                info.insert(0, ssid)
                # append left over
                info.append(line[83:].strip())
                connection_info[ssid] = info
            if if_wlan_disable(card):
                connection_stat = {
                    "connection": "Disabled",
                    "ssid": None,
                }
            elif not if_statue(card):
                connection_stat = {
                    "connection": "Disconnected",
                    "ssid": None,
                }
            else:
                ssid = get_ssid(card)
                connection_stat = {
                    "connection": "Connected",
                    "ssid": ssid,
                }
            second_dictionary = {
                'state': connection_stat,
                'info': connection_info
            }
        else:
            if card_online(card):
                connection_stat = {"connection": "Connected"}
            elif if_card_connected(card):
                connection_stat = {"connection": "Disconnected"}
            else:
                connection_stat = {"connection": "Unplug"}
            second_dictionary = {'state': connection_stat, 'info': None}
        cards[card] = second_dictionary
    main_dictionary['cards'] = cards
    return main_dictionary


def connection_status(card: str, network_info: dict) -> str:
    if card is None:
        net_state = "Network card is not enabled"
    elif 'wlan' in card:
        if not if_wlan_disable(card) and if_statue(card):
            cmd1 = "ifconfig %s | grep ssid" % card
            cmd2 = "ifconfig %s | grep 'inet '" % card
            out1 = Popen(cmd1, shell=True, stdout=PIPE, universal_newlines=True)
            out2 = Popen(cmd2, shell=True, stdout=PIPE, universal_newlines=True)
            ssid_info = out1.stdout.read().strip()
            inet_info = out2.stdout.read().strip()
            ssid = network_info['cards'][card]['state']["ssid"]
            percentage = network_info['cards'][card]['info'][ssid][4]
            net_state = f"Signal Strength: {percentage}% \n{ssid_info} \n{subnet_hex_to_dec(inet_info)}"
        else:
            net_state = "WiFi %s not connected" % card
    else:
        cmd = "ifconfig %s | grep 'inet '" % card
        out = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
        line = out.stdout.read().strip()
        net_state = subnet_hex_to_dec(line)
    return net_state


def switch_default(nic):
    nics = nics_list()
    nics.remove(nic)
    if not nics:
        return
    for card in nics:
        nic_info = Popen(
            ['ifconfig', card],
            stdout=PIPE,
            close_fds=True,
            universal_newlines=True
        ).stdout.read()
        if 'status: active' in nic_info or 'status: associated' in nic_info:
            if 'inet ' in nic_info or 'inet6' in nic_info:
                run(f'service dhclient restart {card}', shell=True)
                break
    return


def restart_all_nics(widget):
    run('service netif restart', shell=True)


def stopallnetwork():
    run('service netif stop', shell=True)


def start_all_network():
    run('service netif start', shell=True)


def start_network_card(net_card):
    run(f'service netif start {net_card}', shell=True)
    sleep(1)
    run('service routing restart', shell=True)
    run(f'service dhclient start {net_card}', shell=True)


def stop_network_card(net_card):
    run(f'service netif stop {net_card}', shell=True)
    switch_default(net_card)


def restart_card_network(net_card):
    run(f'service netif restart {net_card}', shell=True)


def restart_routing_and_dhcp(net_card):
    run('service routing restart', shell=True)
    sleep(1)
    run(f'service dhclient restart {net_card}', shell=True)


def start_static_network(net_card, inet, netmask):
    run(f'ifconfig {net_card} inet {inet} netmask {netmask}', shell=True)
    sleep(1)
    run('service routing restart', shell=True)


def wifi_disconnection(wifi_card):
    run(f'ifconfig {wifi_card} down', shell=True)
    run(f"ifconfig {wifi_card} ssid 'none'", shell=True)
    run(f'ifconfig {wifi_card} up', shell=True)


def disable_wifi(wifi_card):
    run(f'ifconfig {wifi_card} down', shell=True)


def enable_wifi(wifi_card):
    run(f'ifconfig {wifi_card} up', shell=True)
    run(f'ifconfig {wifi_card} up scan', shell=True)


def connect_to_ssid(name, wifi_card):
    run('killall wpa_supplicant', shell=True)
    # service
    sleep(0.5)
    run(f"ifconfig {wifi_card} ssid '{name}'", shell=True)
    sleep(0.5)
    wpa_supplicant = run(
        f'wpa_supplicant -B -i {wifi_card} -c /etc/wpa_supplicant.conf',
        shell=True
    )
    return wpa_supplicant.returncode == 0


def subnet_hex_to_dec(ifconfig_string):
    snethex = re.search('0x.{8}', ifconfig_string).group(0)[2:]
    snethexlist = re.findall('..', snethex)
    snetdec = ".".join(str(int(li, 16)) for li in snethexlist)
    outputline = ifconfig_string.replace(re.search('0x.{8}', ifconfig_string).group(0), snetdec)
    return outputline


def get_ssid_wpa_supplicant_config(ssid):
    cmd = f"""grep -A 3 'ssid="{ssid}"' /etc/wpa_supplicant.conf"""
    out = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    return out.stdout.read().splitlines()


def delete_ssid_wpa_supplicant_config(ssid):
    cmd = f"""awk '/sid="{ssid}"/ """ \
        """{print NR-2 "," NR+4 "d"}' """ \
        """/etc/wpa_supplicant.conf | sed -f - /etc/wpa_supplicant.conf"""
    out = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    left_over = out.stdout.read()
    wpa_supplicant_conf = open('/etc/wpa_supplicant.conf', 'w')
    wpa_supplicant_conf.writelines(left_over)
    wpa_supplicant_conf.close()


def nic_status(card):
    out = Popen(
        f'ifconfig {card} | grep status:',
        shell=True, stdout=PIPE,
        universal_newlines=True
    )
    return out.stdout.read().split(':')[1].strip()


def start_dhcp(wifi_card):
    run(f'dhclient {wifi_card}', shell=True)


def wait_inet(card):
    ip_regex = r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+'
    status = 'associated' if 'wlan' in card else 'active'
    while nic_status(card) != status:
        sleep(0.1)
        print(nic_status(card))
    while True:
        ifcmd = f"ifconfig -f inet:dotted {card}"
        if_output = check_output(ifcmd.split(" "), universal_newlines=True)
        print(if_output)
        re_ip = re.search(fr'inet {ip_regex}', if_output)
        if re_ip and '0.0.0.0' not in re_ip.group():
            print(re_ip)
            break
