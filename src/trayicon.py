#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject, GLib
import gettext
from time import sleep
import threading
import _thread
from sys import path
import locale

gettext.bindtextdomain('networkmgr', '/usr/local/share/locale')
gettext.textdomain('networkmgr')
_ = gettext.gettext

path.append("/usr/local/share/networkmgr")
from net_api import (
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
    wlan_status
)

encoding = locale.getpreferredencoding()
threadBreak = False
GObject.threads_init()


class trayIcon(object):

    def stop_manager(self, widget):
        Gtk.main_quit()

    def __init__(self):
        self.statusIcon = Gtk.StatusIcon()
        self.statusIcon.set_visible(True)
        self.statusIcon.connect("activate", self.leftclick)
        self.statusIcon.connect('popup-menu', self.icon_clicked)

    def leftclick(self, status_icon):
        if not self.thr.is_alive():
            self.thr.start()
        button = 1
        time = Gtk.get_current_event_time()
        position = Gtk.StatusIcon.position_menu
        self.nm_menu().popup(None, None, position, status_icon, button, time)

    def icon_clicked(self, status_icon, button, time):
        if not self.thr.is_alive():
            self.thr.start()
        position = Gtk.StatusIcon.position_menu
        self.nm_menu().popup(None, None, position, status_icon, button, time)

    def nm_menu(self):
        self.menu = Gtk.Menu()
        e_title = Gtk.MenuItem()
        e_title.set_label(_("Ethernet Network"))
        e_title.set_sensitive(False)
        self.menu.append(e_title)
        self.menu.append(Gtk.SeparatorMenuItem())
        cardnum = 1
        wifinum = 1
        cards = self.cardinfo['cards']
        for netcard in cards:
            connection_state = cards[netcard]['state']["connection"]
            status_item = Gtk.MenuItem()
            status_item.set_sensitive(False)
            self.menu.append(status_item)
            card_info = {}
            if "wlan" not in netcard:
                if connection_state == "Connected":
                    card_info.update({
                        "label": "Disable",
                        "action": self.disconnectcard,
                    })
                elif connection_state == "Disconnected":
                    card_info.update({
                        "label": "Enable",
                        "action": self.connectcard,
                    })
                else:
                    connection_state = "Unplug"
                if card_info:
                    card_item = Gtk.MenuItem(_(card_info["label"]))
                    card_item.connect("activate", card_info["action"], netcard)
                    self.menu.append(card_item)
                status_item.set_label(_(f"Wired {cardnum} {connection_state}"))
                cardnum += 1
            elif "wlan" in netcard:
                wifi_info = {}
                if connection_state == "Disabled":
                    wifi_info.update({
                        "label": "Enable",
                        "action": self.enable_Wifi,
                    })
                elif connection_state == "Disconnected":
                    self.wifiListMenu(netcard, None, False, cards)
                    wifi_info.update({
                        "label": "Disable",
                        "action": self.disable_Wifi,
                    })
                else:
                    connection_state = "Connected"
                    wifi_info.update({
                        "label": "Disable",
                        "action": self.disable_Wifi,
                    })
                    ssid = cards[netcard]['state']["ssid"]
                    bar = cards[netcard]['info'][ssid][4]
                    connection_item = Gtk.ImageMenuItem(ssid)
                    connection_item.set_image(self.wifi_signal_icon(bar))
                    connection_item.show()
                    disconnect_item = Gtk.MenuItem(_(f"Disconnect from {ssid}"))
                    disconnect_item.connect("activate", self.disconnect_wifi,
                                            netcard)
                    self.menu.append(connection_item)
                    self.menu.append(disconnect_item)
                    self.wifiListMenu(netcard, ssid, True, cards)
                status_item.set_label(_(f"WiFi {wifinum} {connection_state}"))
                action_item = Gtk.MenuItem(_(f"{wifi_info['label']} Wifi {wifinum}"))
                action_item.connect("activate", wifi_info['action'], netcard)
                self.menu.append(action_item)
                wifinum += 1
            self.menu.append(Gtk.SeparatorMenuItem())

        if openrc:
            if not self.cardinfo['service']:
                label = _("Enable Networking")
                action = self.openNetwork
            else:
                label = _("Disable Networking")
                action = self.closeNetwork
            item = Gtk.MenuItem(label)
            item.connect("activate", action)
            self.menu.append(item)
        else:
            print('service netif status not supported')
        close_manager = Gtk.MenuItem(_("Close Network Manager"))
        close_manager.connect("activate", self.stop_manager)
        self.menu.append(close_manager)
        self.menu.show_all()
        return self.menu

    def ssid_menu_item(self, caps, ssid, ssid_info):
        menu_item = Gtk.ImageMenuItem(ssid)
        if caps in ('E', 'ES'):
            is_secure = False
            click_action = self.menu_click_open
            ssid_type = ssid
        else:
            is_secure = True
            click_action = self.menu_click_lock
            ssid_type = ssid_info
        menu_item.set_image(self.wifi_signal_icon(sn, is_secure))
        menu_item.connect("activate", click_action, ssid_type, wificard)
        menu_item.show()
        return menu_item

    def wifiListMenu(self, wificard, cssid, passes, cards):
        wiconncmenu = Gtk.Menu()
        avconnmenu = Gtk.MenuItem(_("Available Connections"))
        avconnmenu.set_submenu(wiconncmenu)
        for ssid in cards[wificard]['info']:
            ssid_info = cards[wificard]['info'][ssid]
            ssid = cards[wificard]['info'][ssid][0]
            sn = cards[wificard]['info'][ssid][4]
            caps = cards[wificard]['info'][ssid][6]
            if passes:
                if cssid != ssid:
                    menu_item = self.ssid_menu_item(caps, ssid, ssid_info)
                    wiconncmenu.append(menu_item)
            else:
                menu_item = self.ssid_menu_item(caps, ssid, ssid_info)
                wiconncmenu.append(menu_item)
        self.menu.append(avconnmenu)

    def menu_click_open(self, widget, ssid, wificard):
        if f'"{ssid}"' in open("/etc/wpa_supplicant.conf").read():
            connectToSsid(ssid, wificard)
        else:
            self.Open_Wpa_Supplicant(ssid, wificard)
        self.updateinfo()

    def menu_click_lock(self, widget, ssid_info, wificard):
        if f'"{ssid_info[0]}"' in open('/etc/wpa_supplicant.conf').read():
            connectToSsid(ssid_info[0], wificard)
        else:
            self.Authentication(ssid_info, wificard, False)
        self.updateinfo()

    def disconnect_wifi(self, widget, wificard):
        wifiDisconnection(wificard)
        self.updateinfo()

    def disable_Wifi(self, widget, wificard):
        disableWifi(wificard)
        self.updateinfo()

    def enable_Wifi(self, widget, wificard):
        enableWifi(wificard)
        self.updateinfo()

    def connectcard(self, widget, netcard):
        startnetworkcard(netcard)
        self.updateinfo()

    def disconnectcard(self, widget, netcard):
        stopnetworkcard(netcard)
        self.updateinfo()

    def closeNetwork(self, widget):
        stopallnetwork()
        self.updateinfo()

    def openNetwork(self, widget):
        startallnetwork()
        self.updateinfo()

    def signal_icon_name(self, bar, suffix):
        if bar > 75:
            icon_name = f"nm-signal-100{suffix}"
        elif bar > 50:
            icon_name = f"nm-signal-75{suffix}"
        elif bar > 25:
            icon_name = f"nm-signal-50{suffix}"
        elif bar > 5:
            icon_name = f"nm-signal-25{suffix}"
        else:
            icon_name = f"nm-signal-00{suffix}"
        return icon_name

    def wifi_signal_icon(self, bar, is_secure=False):
        img = Gtk.Image()
        suffix = ""
        if is_secure:
            suffix = "-secure"
        icon_name = self.signal_icon_name(bar, suffix)
        img.set_from_icon_name(icon_name, Gtk.IconSize.MENU)
        img.show()
        return img

    def updateinfo(self):
        if not self.if_running:
            self.if_running = True
            self.cardinfo = networkdictionary()
            defaultcard = self.cardinfo['default']
            default_type = self.network_type(defaultcard)
            GLib.idle_add(self.updatetray, defaultcard, default_type)
            self.if_running = False

    def updatetray(self, defaultdev, default_type):
        self.updatetrayicon(defaultdev, default_type)
        self.trayStatus(defaultdev)

    def updatetrayloop(self):
        while True:
            self.updateinfo()
            sleep(20)

    def network_type(self, defaultdev):
        if defaultdev is None:
            return None
        elif 'wlan' in defaultdev:
            return 'wifi'
        else:
            return 'wire'

    def default_wifi_state(self, defaultdev):
        info = self.cardinfo['cards'][defaultdev]
        if info['state']["connection"] == "Connected":
            ssid = info['state']["ssid"]
            return info['info'][ssid][4]
        else:
            return None

    def updatetrayicon(self, defaultdev, card_type):
        if card_type is None:
            icon_name = 'nm-no-connection'
        elif card_type == 'wire':
            icon_name = 'nm-device-wired'
        else:
            wifi_state = self.default_wifi_state(defaultdev)
            if wifi_state is None:
                icon_name = 'nm-no-connection'
            elif wifi_state > 80:
                icon_name = 'nm-signal-100'
            elif wifi_state > 60:
                icon_name = 'nm-signal-75'
            elif wifi_state > 40:
                icon_name = 'nm-signal-50'
            elif wifi_state > 20:
                icon_name = 'nm-signal-25'
            else:
                icon_name = 'nm-signal-00'
        self.statusIcon.set_from_icon_name(icon_name)

    def trayStatus(self, defaultdev):
        self.statusIcon.set_tooltip_text(connectionStatus(defaultdev))

    def tray(self):
        self.if_running = False
        self.thr = threading.Thread(target=self.updatetrayloop)
        self.thr.setDaemon(True)
        self.thr.start()
        Gtk.main()

    def close(self, widget):
        self.window.hide()

    def add_to_wpa_supplicant(self, widget, ssid_info, card):
        pwd = self.password.get_text()
        self.setup_wpa_supplicant(ssid_info[0], ssid_info, pwd, card)
        _thread.start_new_thread(
            self.try_to_connect_to_ssid,
            (ssid_info[0], ssid_info, card)
        )
        self.window.hide()

    def try_to_connect_to_ssid(self, ssid, ssid_info, card):
        if not connectToSsid(ssid, card):
            delete_ssid_wpa_supplicant_config(ssid)
            GLib.idle_add(self.restart_authentication, ssid_info, card)
        else:
            for _ in range(60):
                if wlan_status(card) == 'associated':
                    self.updateinfo()
                    break
                sleep(1)
            else:
                delete_ssid_wpa_supplicant_config(ssid)
                GLib.idle_add(self.restart_authentication, ssid_info, card)
        return

    def restart_authentication(self, ssid_info, card):
        self.Authentication(ssid_info, card, True)

    def on_check(self, widget):
        self.password.set_visibility(widget.get_active())

    def Authentication(self, ssid_info, card, failed):
        self.window = Gtk.Window()
        self.window.set_title(_("Wi-Fi Network Authentication Required"))
        self.window.set_border_width(0)
        self.window.set_size_request(500, 200)
        box1 = Gtk.VBox(False, 0)
        self.window.add(box1)
        box1.show()
        box2 = Gtk.VBox(False, 10)
        box2.set_border_width(10)
        box1.pack_start(box2, True, True, 0)
        box2.show()
        # Creating MBR or GPT drive
        if failed:
            title = _(f"{ssid_info[0]} Wi-Fi Network Authentication failed")
        else:
            title = _(f"Authentication required by {ssid_info[0]} Wi-Fi Network")
        label = Gtk.Label(f"<b><span size='large'>{title}</span></b>")
        label.set_use_markup(True)
        pwd_label = Gtk.Label(_("Password:"))
        self.password = Gtk.Entry()
        self.password.set_visibility(False)
        check = Gtk.CheckButton(_("Show password"))
        check.connect("toggled", self.on_check)
        table = Gtk.Table(1, 2, True)
        table.attach(label, 0, 5, 0, 1)
        table.attach(pwd_label, 1, 2, 2, 3)
        table.attach(self.password, 2, 4, 2, 3)
        table.attach(check, 2, 4, 3, 4)
        box2.pack_start(table, False, False, 0)
        box2 = Gtk.HBox(False, 10)
        box2.set_border_width(5)
        box1.pack_start(box2, False, True, 0)
        box2.show()
        # Add create_scheme button
        cancel = Gtk.Button(stock=Gtk.STOCK_CANCEL)
        cancel.connect("clicked", self.close)
        connect = Gtk.Button(stock=Gtk.STOCK_CONNECT)
        connect.connect("clicked", self.add_to_wpa_supplicant, ssid_info, card)
        table = Gtk.Table(1, 2, True)
        table.set_col_spacings(10)
        table.attach(connect, 4, 5, 0, 1)
        table.attach(cancel, 3, 4, 0, 1)
        box2.pack_end(table, True, True, 5)
        self.window.show_all()
        return 'Done'

    def setup_wpa_supplicant(self, ssid, ssid_info, pwd, card):
        if 'RSN' in ssid_info[-1]:
            # /etc/wpa_supplicant.conf written by networkmgr
            ws = '\nnetwork={'
            ws += f'\n ssid="{ssid}"'
            ws += '\n key_mgmt=WPA-PSK'
            ws += '\n proto=RSN'
            ws += f'\n psk="{pwd}"\n'
            ws += '}\n'
        elif 'WPA' in ssid_info[-1]:
            ws = '\nnetwork={'
            ws += f'\n ssid="{ssid}"'
            ws += '\n key_mgmt=WPA-PSK'
            ws += '\n proto=WPA'
            ws += f'\n psk="{pwd}"\n'
            ws += '}\n'
        else:
            ws = '\nnetwork={'
            ws += f'\n ssid="{ssid}"'
            ws += '\n key_mgmt=NONE'
            ws += '\n wep_tx_keyidx=0'
            ws += f'\n wep_key0={pwd}\n'
            ws += '}\n'
        wsf = open("/etc/wpa_supplicant.conf", 'a')
        wsf.writelines(ws)
        wsf.close()

    def Open_Wpa_Supplicant(self, ssid, card):
        ws = '\nnetwork={'
        ws += f'\n ssid="{ssid}"'
        ws += '\n key_mgmt=NONE\n}\n'
        wsf = open("/etc/wpa_supplicant.conf", 'a')
        wsf.writelines(ws)
        wsf.close()
