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


def test_default_card_returns_str():
    """test for src.net_api.defaultcard"""
    result = defaultcard()
    assert isinstance(result, str)


# TODO: mock subprocess to return empty list

def test_card_online():
    net_card = defaultcard()
    result = card_online(net_card)
    assert result


def test_card_not_online():
    net_card = "em99"
    result = card_online(net_card)
    assert not result


def test_connection_status_card_is_none():
    """test for src.net_api.connectionStatus"""
    card = None
    result = connectionStatus(card)
    assert isinstance(result, str)
    assert "Network card is not enabled" == result


def test_connection_status_card_is_default():
    """test for src.net_api.connectionStatus"""
    card = defaultcard()
    result = connectionStatus(card)
    assert isinstance(result, str)
    assert "inet" in result
    assert "netmask" in result
    assert "broadcast" in result


def test_connection_status_card_is_wlan_not_connected():
    """test for src.net_api.connectionStatus"""
    card = 'wlan99'
    result = connectionStatus(card)
    assert isinstance(result, str)
    assert f"WiFi {card} not connected" in result


def test_connection_status_card_is_wlan_connected():
    """test for src.net_api.connectionStatus"""
    card = 'wlan0'
    result = connectionStatus(card)
    assert isinstance(result, str)
    assert "inet" in result
    assert "ssid" in result
    assert "netmask" in result
    assert "broadcast" in result
