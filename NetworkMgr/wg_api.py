#!/usr/bin/env python

"""WireGuard tunnel discovery and control.

Lists the tunnel configurations under $PREFIX/etc/wireguard, reports which
are running, and brings them up or down through the wireguard rc service.
"""

import os
import sys
from platform import system
from subprocess import PIPE, run

PREFIX = '/usr/local' if system() == 'FreeBSD' else sys.prefix
WG_CONFIG_PATH = f'{PREFIX}/etc/wireguard/'


def wg_service_state():
    """Report whether rc is set to manage the WireGuard tunnels.

    Asked through sysrc rather than `service wireguard rcvar`, which answers
    the same question but wraps it in four lines of prose that have to be
    parsed, and quotes the value so every caller has to compare against
    '"NO"'. sysrc gives the bare value.

    Returns:
        str: 'YES' or 'NO'. A variable set nowhere reads as 'NO', which is
            the rc script's own default: line 69 of
            /usr/local/etc/rc.d/wireguard is `: ${wireguard_enable="NO"}`,
            and sysrc reports an unset variable as an error rather than a
            value.
    """
    result = run(['sysrc', '-n', 'wireguard_enable'],
                 stdout=PIPE, stderr=PIPE, check=False, text=True)
    if result.returncode != 0:
        return 'NO'
    return result.stdout.strip() or 'NO'


def wg_dictionary(service_state):
    """Collect the WireGuard tunnels and their state.

    The service state is passed in rather than read here. Asking rc for it
    costs about 13 ms of shell, against under 1 ms for everything else in
    this function, and `wireguard_enable` only changes when someone edits
    rc.conf. Reading it once and handing it down keeps the tray refresh
    cheap.

    Args:
        service_state (str): 'YES' or 'NO' from wg_service_state().

    Returns:
        dict: 'service' as given, 'default', and 'configs' mapping each
            tunnel device to its 'state' and its 'info' display name.
    """
    maindictionary = {
        'service': service_state,
        'default': '',
    }
    configs = {}

    if os.path.exists(WG_CONFIG_PATH):
        wgconfigs = sorted(os.listdir(WG_CONFIG_PATH))
        for wgconfig in wgconfigs:
            wg_device = wgconfig.replace('.conf', '')
            wg_state = wg_status(wg_device)
            wg_name = wg_device
            with open(WG_CONFIG_PATH + wgconfig, encoding="utf-8") as content:
                for line in content:
                    if "# Name = " in line:
                        wg_name = line.split('=')[1].strip()
                        break

            seconddictionary = { 'state': wg_state, 'info': wg_name }
            configs[wg_device] = seconddictionary

    maindictionary['configs'] = configs
    return maindictionary


def disable_wg(wgconfig):
    """Take the specified WireGuard configuration (device) down.

    Args:
        wgconfig (str): the tunnel's configuration name, without .conf.
    """
    run(['wg-quick', 'down', wgconfig], check=False)


def enable_wg(wgconfig):
    """Bring the specified WireGuard configuration (device) up.

    Args:
        wgconfig (str): the tunnel's configuration name, without .conf.
    """
    run(['wg-quick', 'up', wgconfig], check=False)


def wg_status(wgconfig):
    """Function returning the WireGuard configuration (device) is connected or not."""
    result = run(['wg', 'show', wgconfig], stdout=PIPE, stderr=PIPE, check=False)
    out = result.stdout.decode('utf-8')
    error = result.stderr.decode('utf-8')

    if len(out) == 0 and 'Unable to access interface: Device not configured' in error:
        status = "Disconnected"
    else:
        status = "Connected"

    return status
