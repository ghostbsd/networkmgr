import sys
from pathlib import Path

top_dir = str(Path(__file__).absolute().parent.parent.parent)

try:
    from src.net_api import (
        stopnetworkcard,
        startnetworkcard,
        wifiDisconnection,
        stopallnetwork,
        startallnetwork,
        connectToSsid,
        disableWifi,
        enableWifi,
        connectionStatus,
        networkdictionary,
        openrc,
        delete_ssid_wpa_supplicant_config,
        wlan_status,
        card_online,
        defaultcard
    )
except ImportError:
    sys.path.append(top_dir)
    from src.net_api import (
        stopnetworkcard,
        startnetworkcard,
        wifiDisconnection,
        stopallnetwork,
        startallnetwork,
        connectToSsid,
        disableWifi,
        enableWifi,
        connectionStatus,
        networkdictionary,
        openrc,
        delete_ssid_wpa_supplicant_config,
        wlan_status,
        card_online,
        defaultcard
    )


def test_defaultcard_returns_str():
    result = defaultcard()
    assert isinstance(result, str)

def test_card_online():
    netcard = defaultcard()
    result = card_online(netcard)
    assert result

def test_card_not_online():
    netcard = "em99"
    result = card_online(netcard)
    assert not result
