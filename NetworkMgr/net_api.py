#!/usr/bin/env python

import re
from subprocess import Popen, PIPE, run, check_output
from time import sleep
from typing import Optional, Dict, Any, List


def card_online(net_card: str) -> bool:
    """
    Check if a network card is online.

    Args:
        net_card: The name of the network card to check.

    Returns:
        True if the network card is online, False otherwise.
    """
    lan = Popen('ifconfig ' + net_card, shell=True, stdout=PIPE, universal_newlines=True)
    return 'inet ' in lan.stdout.read()


def default_card() -> Optional[str]:
    """
    Get the default network card.

    Returns:
        The default network card if one exists, None otherwise.
    """
    cmd = "netstat -rn | grep default"
    nics = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    device = nics.stdout.readlines()
    if len(device) == 0:
        return None
    return list(filter(None, device[0].rstrip().split()))[3]


def if_wlan_disable(wifi_card: str) -> bool:
    """
    Check if a Wi-Fi card is disabled.

    Args:
        wifi_card: The name of the Wi-Fi card to check.

    Returns:
        True if the Wi-Fi card is disabled, False otherwise.
    """
    cmd = f"ifconfig {wifi_card} list scan"
    nics = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    return not nics.stdout.read()


def if_statue(wifi_card: str) -> bool:
    """
    Check if a Wi-Fi card is associated with a network.

    Args:
        wifi_card: The name of the Wi-Fi card to check.

    Returns:
        True if the Wi-Fi card is associated, False otherwise.
    """
    cmd = f"ifconfig {wifi_card}"
    wl = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    wlout = wl.stdout.read()
    return "associated" in wlout


def get_ssid(wifi_card: str) -> str:
    """
    Get the SSID of a connected Wi-Fi card.

    Args:
        wifi_card: The name of the Wi-Fi card.

    Returns:
        The SSID of the Wi-Fi network.
    """
    card = f'ifconfig {wifi_card} | grep ssid'
    wlan = Popen(card, shell=True, stdout=PIPE, universal_newlines=True)
    # If there are quotation marks in the string, use that as a separator,
    # otherwise use the default whitespace. This is to handle ssid strings
    # with spaces in them. These ssid strings will be double-quoted by ifconfig
    temp = wlan.stdout.readlines()[0].rstrip()
    if '"' in temp:
        return temp.split('"')[1]
    return temp.split()[1]


def nics_list() -> list[str]:
    """
    Get a sorted list of network interfaces excluding non-NIC interfaces.

    Returns:
        A sorted list of network interface names.
    """
    not_nics_regex = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|" \
                    r"faith|ppp|bridge|wg)[0-9]+(\s*)|vm-[a-z]+(\s*)"
    nics = Popen('ifconfig -l', shell=True, stdout=PIPE, universal_newlines=True).stdout.read().strip()
    return sorted(re.sub(not_nics_regex, '', nics).strip().split())


def if_card_connected(net_card: str) -> bool:
    """
    Check if a network card is connected.

    Args:
        net_card: The name of the network card.

    Returns:
        True if the network card is connected, False otherwise.
    """
    wifi = Popen(f'ifconfig {net_card}', shell=True, stdout=PIPE, universal_newlines=True)
    return 'status: active' in wifi.stdout.read()


def calculate_signal_strength_percentage(signal: str) -> int:
    """
    Calculate the signal strength percentage from signal and noise values.

    Args:
        signal: The signal strength string in the format "signal:noise".

    Returns:
        The signal strength percentage.
    """
    sig = int(signal.partition(':')[0])
    noise = int(signal.partition(':')[2])
    return int((sig - noise) * 4)


def network_service_state():
    return False


def network_dictionary() -> Dict[str, Any]:
    """
    Generate a dictionary with network card information and states.

    Returns:
        A dictionary containing the network service state, default network card,
        and a dictionary of network cards with their state and connection information.
    """
    nlist = nics_list()
    main_dictionary = {
        'service': network_service_state(),
        'default': default_card(),
        'cards': {}
    }

    for card in nlist:
        if 'wlan' in card:
            connection_info = get_wifi_info(card)
            connection_stat = get_wlan_connection_status(card)
        else:
            connection_info = None
            connection_stat = get_ethernet_connection_status(card)

        main_dictionary['cards'][card] = {
            'state': connection_stat,
            'info': connection_info
        }

    return main_dictionary


def get_wifi_info(card: str) -> Dict[str, List[str]]:
    """
    Retrieve Wi-Fi connection information for the specified wireless card.

    Args:
        card (str): The name of the wireless network card.

    Returns:
        Dict[str, List[str]]: A dictionary where each key is an SSID and the value is a list of related connection details.
    """
    scanv = f"ifconfig {card} list scan | grep -va BSSID"
    wifi = Popen(scanv, shell=True, stdout=PIPE, universal_newlines=True)
    connection_info: Dict[str, List[str]] = {}

    for line in wifi.stdout:
        if line.startswith(" " * 5):
            continue
        ssid = line[:33].strip()
        info: list[str] = line[:83][33:].strip().split()
        percentage = calculate_signal_strength_percentage(info[3])

        if ssid in connection_info and int(connection_info[ssid][4]) > percentage:
            continue

        info[3] = str(percentage)
        info.insert(0, ssid)
        info.append(line[83:].strip())
        connection_info[ssid] = info

    return connection_info


def get_wlan_connection_status(card: str) -> Dict[str, Optional[str]]:
    """
    Retrieve the connection status for a wireless network card.

    Args:
        card (str): The name of the wireless network card.

    Returns:
        Dict[str, Optional[str]]: A dictionary containing the connection status ('Connected',
                                'Disconnected', or 'Disabled') and the SSID if connected.
    """
    if if_wlan_disable(card):
        return {"connection": "Disabled", "ssid": None}
    elif not if_statue(card):
        return {"connection": "Disconnected", "ssid": None}
    else:
        return {"connection": "Connected", "ssid": get_ssid(card)}


def get_ethernet_connection_status(card: str) -> Dict[str, str]:
    """
    Retrieve the connection status for an Ethernet network card.

    Args:
        card (str): The name of the Ethernet network card.

    Returns:
        Dict[str, str]: A dictionary containing the connection status ('Connected', 'Disconnected', or 'Unplug').
    """
    if card_online(card):
        return {"connection": "Connected"}
    elif if_card_connected(card):
        return {"connection": "Disconnected"}
    else:
        return {"connection": "Unplug"}



def connection_status(card: str, network_info: dict) -> str:
    if card is None:
        return "Network card is not enabled"
    elif 'wlan' in card:
        if not if_wlan_disable(card) and if_statue(card):
            cmd1 = f"ifconfig {card} | grep ssid"
            cmd2 = f"ifconfig {card} | grep 'inet '"
            out1 = Popen(cmd1, shell=True, stdout=PIPE, universal_newlines=True)
            out2 = Popen(cmd2, shell=True, stdout=PIPE, universal_newlines=True)
            ssid_info = out1.stdout.read().strip()
            inet_info = out2.stdout.read().strip()
            ssid = network_info['cards'][card]['state']["ssid"]
            percentage = network_info['cards'][card]['info'][ssid][4]
            return f"Signal Strength: {percentage}% \n{ssid_info} \n{subnet_hex_to_dec(inet_info)}"
        return f"WiFi {card} not connected"
    else:
        cmd = f"ifconfig {card} | grep 'inet '"
        out = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
        line = out.stdout.read().strip()
        return subnet_hex_to_dec(line)


def switch_default(nic: str) -> None:
    """
    Switch the default network card to a new one.

    Args:
        nic: The network card to switch to.
    """
    nics = nics_list()
    nics.remove(nic)
    if not nics:
        return
    for card in nics:
        nic_info = Popen(['ifconfig', card], stdout=PIPE, close_fds=True, universal_newlines=True).stdout.read()
        if 'status: active' in nic_info or 'status: associated' in nic_info:
            if 'inet ' in nic_info or 'inet6' in nic_info:
                run(f'service dhclient restart {card}', shell=True)
                break


def restart_all_nics(widget):
    run('service netif restart', shell=True)


def stop_all_network() -> None:
    """
    Stop all network services.
    """
    run('service netif stop', shell=True)


def start_all_network() -> None:
    """
    Start all network services.
    """
    run('service netif start', shell=True)


def start_network_card(net_card: str) -> None:
    """
    Start a specific network card.

    Args:
        net_card: The name of the network card to start.
    """
    run(f'service netif start {net_card}', shell=True)
    sleep(1)
    run('service routing restart', shell=True)
    run(f'service dhclient start {net_card}', shell=True)


def stop_network_card(net_card: str) -> None:
    """
    Stop a specific network card and switch default if necessary.

    Args:
        net_card: The name of the network card to stop.
    """
    run(f'service netif stop {net_card}', shell=True)
    switch_default(net_card)


def restart_card_network(net_card: str) -> None:
    """
    Restart a specific network card.

    Args:
        net_card: The name of the network card to restart.
    """
    run(f'service netif restart {net_card}', shell=True)


def restart_routing_and_dhcp(net_card: str) -> None:
    """
    Restart routing and DHCP for a specific network card.

    Args:
        net_card: The name of the network card.
    """
    run('service routing restart', shell=True)
    sleep(1)
    run(f'service dhclient restart {net_card}', shell=True)


def start_static_network(net_card: str, inet: str, netmask: str) -> None:
    """
    Configure a network card with a static IP address and netmask.

    Args:
        net_card: The name of the network card.
        inet: The IP address.
        netmask: The netmask.
    """
    run(f'ifconfig {net_card} inet {inet} netmask {netmask}', shell=True)
    sleep(1)
    run('service routing restart', shell=True)


def wifi_disconnection(wifi_card: str) -> None:
    """
    Disconnect a Wi-Fi card.

    Args:
        wifi_card: The name of the Wi-Fi card to disconnect.
    """
    run(f'ifconfig {wifi_card} down', shell=True)
    run(f"ifconfig {wifi_card} ssid 'none'", shell=True)
    run(f'ifconfig {wifi_card} up', shell=True)


def disable_wifi(wifi_card: str) -> None:
    """
    Disable a Wi-Fi card.

    Args:
        wifi_card: The name of the Wi-Fi card to disable.
    """
    run(f'ifconfig {wifi_card} down', shell=True)


def enable_wifi(wifi_card: str) -> None:
    """
    Enable and scan for networks on a Wi-Fi card.

    Args:
        wifi_card: The name of the Wi-Fi card to enable.
    """
    run(f'ifconfig {wifi_card} up', shell=True)
    run(f'ifconfig {wifi_card} up scan', shell=True)


def connect_to_ssid(name: str, wifi_card: str) -> bool:
    """
    Connect a Wi-Fi card to a specified SSID.

    Args:
        name: The SSID to connect to.
        wifi_card: The name of the Wi-Fi card.

    Returns:
        `True` if the connection was successful, `False` otherwise.
    """
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


def subnet_hex_to_dec(ifconfig_string: str) -> str:
    """
    Convert subnet from hexadecimal to decimal format.

    Args:
        ifconfig_string: The ifconfig output string containing the subnet in hexadecimal.

    Returns:
        The ifconfig output string with the subnet converted to decimal format.
    """
    snethex = re.search('0x.{8}', ifconfig_string).group(0)[2:]
    snethexlist = re.findall('..', snethex)
    snetdec = ".".join(str(int(li, 16)) for li in snethexlist)
    return ifconfig_string.replace(re.search('0x.{8}', ifconfig_string).group(0), snetdec)


def get_ssid_wpa_supplicant_config(ssid: str) -> list[str]:
    """
    Retrieve the WPA supplicant configuration for a specific SSID.

    Args:
        ssid: The SSID to retrieve the configuration for.

    Returns:
        The configuration lines for the specified SSID.
    """
    cmd = f"""grep -A 3 'ssid="{ssid}"' /etc/wpa_supplicant.conf"""
    out = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    return out.stdout.read().splitlines()


def delete_ssid_wpa_supplicant_config(ssid: str) -> None:
    """
    Delete the WPA supplicant configuration for a specific SSID.

    Args:
        ssid: The SSID to delete the configuration for.
    """
    cmd = f"""awk '/ssid="{ssid}"/ {{print NR-2 "," NR+4 "d"}}' """ \
          """ /etc/wpa_supplicant.conf | sed -f - /etc/wpa_supplicant.conf"""
    out = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
    left_over = out.stdout.read()
    with open('/etc/wpa_supplicant.conf', 'w') as wpa_supplicant_conf:
        wpa_supplicant_conf.writelines(left_over)


def nic_status(card: str) -> str:
    """
    Get the status of a network interface card.

    Args:
        card: The name of the network card.

    Returns:
        The status of the network card.
    """
    out = Popen(f'ifconfig {card} | grep status:', shell=True, stdout=PIPE, universal_newlines=True)
    return out.stdout.read().split(':')[1].strip()


def start_dhcp(wifi_card: str) -> None:
    """
    Start DHCP for a Wi-Fi card.

    Args:
        wifi_card: The name of the Wi-Fi card.
    """
    run(f'dhclient {wifi_card}', shell=True)


def wait_inet(card: str) -> None:
    """
    Wait until a network card has an assigned IP address.

    Args:
        card: The name of the network card.
    """
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
