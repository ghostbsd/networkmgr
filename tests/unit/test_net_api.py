import sys
from pathlib import Path
from subprocess import Popen
import subprocess

import pytest

top_dir = str(Path(__file__).absolute().parent.parent.parent)

try:
    from src.net_api import (
        card_online,
        connectionStatus,
        connectToSsid,
        defaultcard,
        delete_ssid_wpa_supplicant_config,
        disableWifi,
        enableWifi,
        networkdictionary,
        openrc,
        startallnetwork,
        startnetworkcard,
        stopallnetwork,
        stopnetworkcard,
        wifiDisconnection,
        wlan_status,
    )
    import src.net_api
except ImportError:
    sys.path.append(top_dir)
    from src.net_api import (
        card_online,
        connectionStatus,
        connectToSsid,
        defaultcard,
        delete_ssid_wpa_supplicant_config,
        disableWifi,
        enableWifi,
        networkdictionary,
        openrc,
        startallnetwork,
        startnetworkcard,
        stopallnetwork,
        stopnetworkcard,
        wifiDisconnection,
        wlan_status,
    )
    import src.net_api


def test_defaultcard_returns_str():
    result = defaultcard()
    assert isinstance(result, str)


# TODO: mock subprocess to return empty list

def test_card_online():
    netcard = defaultcard()
    result = card_online(netcard)
    assert result


def test_card_not_online():
    netcard = "em99"
    result = card_online(netcard)
    assert not result


def test_connectionStatus_card_is_none():
    card = None
    result = connectionStatus(card)
    assert isinstance(result, str)


def test_connectionStatus_card_is_default():
    card = defaultcard()
    result = connectionStatus(card)
    assert isinstance(result, str)
    assert "inet" in result
    assert "netmask" in result
    assert "broadcast" in result


def test_connectionStatus_card_is_wlan_not_connected():
    card = 'wlan00'
    result = connectionStatus(card)
    assert isinstance(result, str)
    assert f"WiFi {card} not connected"
