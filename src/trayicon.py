#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject, GLib
from time import sleep
import threading
import _thread
from sys import path
import locale

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
        e_title.set_label("Ethernet Network")
        e_title.set_sensitive(False)
        self.menu.append(e_title)
        self.menu.append(Gtk.SeparatorMenuItem())
        cardnum = 1
        wifinum = 1
        cards = self.cardinfo['cards']
        for netcard in cards:
            connection_state = cards[netcard]['state']["connection"]
            if "wlan" not in netcard:
                if connection_state == "Connected":
                    wired_item = Gtk.MenuItem("Wired %s Connected" % cardnum)
                    wired_item.set_sensitive(False)
                    self.menu.append(wired_item)
                    disconnect_item = Gtk.ImageMenuItem("Disable")
                    disconnect_item.connect("activate", self.disconnectcard,
                                            netcard)
                    self.menu.append(disconnect_item)
                elif connection_state == "Disconnected":
                    notonline = Gtk.MenuItem("Wired %s Disconnected" % cardnum)
                    notonline.set_sensitive(False)
                    self.menu.append(notonline)
                    wired_item = Gtk.MenuItem("Enable")
                    wired_item.connect("activate", self.connectcard, netcard)
                    self.menu.append(wired_item)
                else:
                    disconnected = Gtk.MenuItem("Wired %s Unplug" % cardnum)
                    disconnected.set_sensitive(False)
                    self.menu.append(disconnected)
                    cardnum += 1
                self.menu.append(Gtk.SeparatorMenuItem())
            elif "wlan" in netcard:
                if connection_state == "Disabled":
                    wd_title = Gtk.MenuItem()
                    wd_title.set_label("WiFi %s Disabled" % wifinum)
                    wd_title.set_sensitive(False)
                    self.menu.append(wd_title)
                    enawifi = Gtk.MenuItem("Enable Wifi %s" % wifinum)
                    enawifi.connect("activate", self.enable_Wifi, netcard)
                    self.menu.append(enawifi)
                elif connection_state == "Disconnected":
                    d_title = Gtk.MenuItem()
                    d_title.set_label("WiFi %s Disconnected" % wifinum)
                    d_title.set_sensitive(False)
                    self.menu.append(d_title)
                    self.wifiListMenu(netcard, None, False, cards)
                    diswifi = Gtk.MenuItem("Disable Wifi %s" % wifinum)
                    diswifi.connect("activate", self.disable_Wifi, netcard)
                    self.menu.append(diswifi)
                else:
                    ssid = cards[netcard]['state']["ssid"]
                    bar = cards[netcard]['info'][ssid][4]
                    wc_title = Gtk.MenuItem("WiFi %s Connected" % wifinum)
                    wc_title.set_sensitive(False)
                    self.menu.append(wc_title)
                    connection_item = Gtk.ImageMenuItem(ssid)
                    connection_item.set_image(self.open_wifi(bar))
                    connection_item.show()
                    disconnect_item = Gtk.MenuItem("Disconnect from %s" % ssid)
                    disconnect_item.connect("activate", self.disconnect_wifi,
                                            netcard)
                    self.menu.append(connection_item)
                    self.menu.append(disconnect_item)
                    self.wifiListMenu(netcard, ssid, True, cards)
                    diswifi = Gtk.MenuItem("Disable Wifi %s" % wifinum)
                    diswifi.connect("activate", self.disable_Wifi, netcard)
                    self.menu.append(diswifi)
                self.menu.append(Gtk.SeparatorMenuItem())
                wifinum += 1

        if openrc is True:
            if self.cardinfo['service'] is False:
                open_item = Gtk.MenuItem("Enable Networking")
                open_item.connect("activate", self.openNetwork)
                self.menu.append(open_item)
            else:
                close_item = Gtk.MenuItem("Disable Networking")
                close_item.connect("activate", self.closeNetwork)
                self.menu.append(close_item)
        else:
            print('service netif status not supported')
        close_manager = Gtk.MenuItem("Close Network Manager")
        close_manager.connect("activate", self.stop_manager)
        self.menu.append(close_manager)
        self.menu.show_all()
        return self.menu

    def wifiListMenu(self, wificard, cssid, passes, cards):
        wiconncmenu = Gtk.Menu()
        avconnmenu = Gtk.MenuItem("Available Connections")
        avconnmenu.set_submenu(wiconncmenu)
        for ssid in cards[wificard]['info']:
            ssid_info = cards[wificard]['info'][ssid]
            ssid = cards[wificard]['info'][ssid][0]
            sn = cards[wificard]['info'][ssid][4]
            caps = cards[wificard]['info'][ssid][6]
            if passes is True:
                if cssid != ssid:
                    menu_item = Gtk.ImageMenuItem(ssid)
                    if caps == 'E' or caps == 'ES':
                        menu_item.set_image(self.open_wifi(sn))
                        menu_item.connect("activate", self.menu_click_open,
                                          ssid, wificard)
                    else:
                        menu_item.set_image(self.secure_wifi(sn))
                        menu_item.connect("activate", self.menu_click_lock,
                                          ssid_info, wificard)
                    menu_item.show()
                    wiconncmenu.append(menu_item)
            else:
                menu_item = Gtk.ImageMenuItem(ssid)
                if caps == 'E' or caps == 'ES':
                    menu_item.set_image(self.open_wifi(sn))
                    menu_item.connect("activate", self.menu_click_open,
                                      ssid, wificard)
                else:
                    menu_item.set_image(self.secure_wifi(sn))
                    menu_item.connect("activate", self.menu_click_lock,
                                      ssid_info, wificard)
                menu_item.show()
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

    def open_wifi(self, bar):
        img = Gtk.Image()
        if bar > 75:
            img.set_from_icon_name("nm-signal-100", Gtk.IconSize.MENU)
        elif bar > 50:
            img.set_from_icon_name("nm-signal-75", Gtk.IconSize.MENU)
        elif bar > 25:
            img.set_from_icon_name("nm-signal-50", Gtk.IconSize.MENU)
        elif bar > 5:
            img.set_from_icon_name("nm-signal-25", Gtk.IconSize.MENU)
        else:
            img.set_from_icon_name("nm-signal-00", Gtk.IconSize.MENU)
        img.show()
        return img

    def secure_wifi(self, bar):
        img = Gtk.Image()
        if bar > 75:
            img.set_from_icon_name("nm-signal-100-secure", Gtk.IconSize.MENU)
        elif bar > 50:
            img.set_from_icon_name("nm-signal-75-secure", Gtk.IconSize.MENU)
        elif bar > 25:
            img.set_from_icon_name("nm-signal-50-secure", Gtk.IconSize.MENU)
        elif bar > 5:
            img.set_from_icon_name("nm-signal-25-secure", Gtk.IconSize.MENU)
        else:
            img.set_from_icon_name("nm-signal-00-secure", Gtk.IconSize.MENU)
        img.show()
        return img

    def updateinfo(self):
        if self.if_running is False:
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
            self.statusIcon.set_from_icon_name('nm-no-connection')
        elif card_type == 'wire':
            self.statusIcon.set_from_icon_name('nm-device-wired')
        else:
            wifi_state = self.default_wifi_state(defaultdev)
            if wifi_state is None:
                self.statusIcon.set_from_icon_name('nm-no-connection')
            elif wifi_state > 80:
                self.statusIcon.set_from_icon_name('nm-signal-100')
            elif wifi_state > 60:
                self.statusIcon.set_from_icon_name('nm-signal-75')
            elif wifi_state > 40:
                self.statusIcon.set_from_icon_name('nm-signal-50')
            elif wifi_state > 20:
                self.statusIcon.set_from_icon_name('nm-signal-25')
            else:
                self.statusIcon.set_from_icon_name('nm-signal-00')

    def trayStatus(self, defaultdev):
        self.statusIcon.set_tooltip_text("%s" % connectionStatus(defaultdev))

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
        if connectToSsid(ssid, card) is False:
            delete_ssid_wpa_supplicant_config(ssid)
            GLib.idle_add(self.restart_authentication, ssid_info, card)
        else:
            for _ in list(range(30)):
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
        if widget.get_active():
            self.password.set_visibility(True)
        else:
            self.password.set_visibility(False)

    def Authentication(self, ssid_info, card, failed):
        self.window = Gtk.Window()
        self.window.set_title("wi-Fi Network Authentication Required")
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
            title = f"{ssid_info[0]} Wi-Fi Network Authentication failed"
        else:
            title = f"Authentication required by {ssid_info[0]} Wi-Fi Network"
        label = Gtk.Label(f"<b><span size='large'>{title}</span></b>")
        label.set_use_markup(True)
        pwd_label = Gtk.Label("Password:")
        self.password = Gtk.Entry()
        self.password.set_visibility(False)
        check = Gtk.CheckButton("Show password")
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
        ws += f'\n ssid={ssid}'
        ws += '\n key_mgmt=NONE\n}\n'
        wsf = open("/etc/wpa_supplicant.conf", 'a')
        wsf.writelines(ws)
        wsf.close()
