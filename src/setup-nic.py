#!/usr/local/bin/python3

"""devd action for IFNET ATTACH events and wireless driver attachments.

Invoked by /usr/local/etc/devd/networkmgr.conf with the interface or device
name as its only argument. Declares the interface in rc.conf if it is not
declared yet, installs or tops up /etc/wpa_supplicant.conf for a wireless
device, and brings the interface up through /etc/pccard_ether.
"""

import os
import re
import shutil
import sys
from pathlib import Path
from subprocess import run


def file_content(paths):
    """Read several files and return their contents joined together.

    Args:
        paths (list[pathlib.Path]): Files to read, in order.

    Returns:
        str: The concatenated contents of every path.
    """
    buffers = []
    for path in paths:
        with path.open('r') as file:
            buffers.append(file.read())
    return "".join(buffers)


def setting_lines(text):
    """Yield the key and the raw line for every key=value line.

    Blank lines and comments are skipped.

    Args:
        text (str): Contents of a wpa_supplicant.conf style file.

    Yields:
        tuple[str, str]: The setting name and the line it came from.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        yield stripped.split('=', 1)[0].strip(), line


def add_missing_settings(conf, template):
    """Prepend the template globals that a config file does not declare yet.

    Args:
        conf (pathlib.Path): Config file to update in place.
        template (pathlib.Path): Template holding the expected globals.
    """
    current = conf.read_text()
    present = {key for key, _ in setting_lines(current)}
    missing = [line for key, line in setting_lines(template.read_text())
               if key not in present]
    if missing:
        conf.write_text("\n".join(missing) + "\n" + current)


args = sys.argv
if len(args) != 2:
    sys.exit(1)
nic = args[1]

etc = Path(os.sep, "etc")
rc_conf = etc / "rc.conf"
rc_conf_local = etc / "rc.conf.local"
wpa_supplicant = etc / "wpa_supplicant.conf"
wpa_supplicant_template = Path("/usr/local/share/networkmgr/wpa_supplicant.conf")

rc_conf_paths = [rc_conf]

if rc_conf_local.exists():
    rc_conf_paths.append(rc_conf_local)

RC_CONF_CONTENT = file_content(rc_conf_paths)

NOT_NICS_REGEX = r"(enc|lo|fwe|fwip|tap|plip|pfsync|pflog|ipfw|tun|sl|faith|" \
    r"ppp|bridge|wg|wlan)[0-9]+|vm-[a-z]+"

# WIFI_DRIVER_REGEX is taken from devd.conf wifi-driver-regex
WIFI_DRIVER_REGEX = "(ath|ath[0-9]+k|bwi|bwn|ipw|iwlwifi|iwi|iwm|iwn|malo|mwl|mt79|otus|" \
    "ral|rsu|rtw|rtwn|rum|run|uath|upgt|ural|urtw|wpi|wtap|zyd)[0-9]+"

if re.search(NOT_NICS_REGEX, nic):
    sys.exit(0)

if re.search(WIFI_DRIVER_REGEX, nic):
    if not wpa_supplicant.exists():
        shutil.copyfile(wpa_supplicant_template, wpa_supplicant)
        shutil.chown(wpa_supplicant, user="root", group="wheel")
        wpa_supplicant.chmod(0o600)  # Secure: root-only, contains passwords
    else:
        add_missing_settings(wpa_supplicant, wpa_supplicant_template)
    if f'wlans_{nic}=' not in RC_CONF_CONTENT:
        for wlan_number in range(9):
            if f'wlan{wlan_number}' not in RC_CONF_CONTENT:
                run(['sysrc', f'wlans_{nic}=wlan{wlan_number}'], check=False)
                run(['sysrc', f'ifconfig_wlan{wlan_number}=WPA DHCP'], check=False)
                break
    run(['/etc/pccard_ether', nic, 'startchildren'], check=False)
else:
    if f'ifconfig_{nic}=' not in RC_CONF_CONTENT:
        run(['sysrc', f'ifconfig_{nic}=DHCP'], check=False)
    run(['/etc/pccard_ether', nic, 'start'], check=False)
