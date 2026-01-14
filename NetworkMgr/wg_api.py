#!/usr/local/bin/python3.11

from platform import system
from subprocess import PIPE, run, os

PREFIX = '/usr/local' if system() == 'FreeBSD' else sys.prefix
WG_CONFIG_PATH = f'{PREFIX}/etc/wireguard/'

def wg_service_state():
    """Function returns the WireGuard service status."""
    result = run(['service', 'wireguard', 'rcvar'], stdout=PIPE, stderr=PIPE, check=False)
    out = result.stdout.decode('utf-8')

    state = 'Unknown'

    for line in out.splitlines():
        if "wireguard_enable=" in line:
            state = line.split('=')[1].strip()
            break

    return state

def wg_dictionary():
    """Function returns the WireGuard configurations."""
    maindictionary = {
        'service': wg_service_state(),
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
    """Function disable the specified WireGuard configuration (device)."""
    run(f'wg-quick down {wgconfig}', shell=True, check=False)

def enable_wg(wgconfig):
    """Function enable the specified WireGuard configuration (device)."""
    run(f'wg-quick up {wgconfig}', shell=True, check=False)

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
