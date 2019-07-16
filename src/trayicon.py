#!/usr/bin/env python3.6

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject, GLib
from time import sleep
import threading
from sys import path
import locale
import os
path.append("/usr/local/share/networkmgr")
from net_api import wiredonlineinfo, stopnetworkcard, isanewnetworkcardinstall
from net_api import startnetworkcard, wifiDisconnection, ifWlan
from net_api import stopallnetwork, startallnetwork, connectToSsid
from net_api import disableWifi, enableWifi
from authentication import Authentication, Open_Wpa_Supplicant
from net_api import connectionStatus, defaultcard
from net_api import restartnetworkcard, networkdictionary
encoding = locale.getpreferredencoding()

threadBreak = False
GObject.threads_init()

wpa_supplican = "/etc/wpa_supplicant.conf"


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
        for netcard in self.cardinfo:
            connection_state = self.cardinfo[netcard]['state']["connection"]
            if "wlan" not in netcard:
                if connection_state == "Connected":
                    wired_item = Gtk.MenuItem("Wired %s Connected" % cardnum)
                    wired_item.connect("activate", self.restartcardconnection,
                                       netcard)
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
                    self.wifiListMenu(netcard, None, False)
                    diswifi = Gtk.MenuItem("Disable Wifi %s" % wifinum)
                    diswifi.connect("activate", self.disable_Wifi, netcard)
                    self.menu.append(diswifi)
                else:
                    ssid = self.cardinfo[netcard]['state']["ssid"]
                    bssid = self.cardinfo[netcard]['state']["bssid"]
                    bar = self.cardinfo[netcard]['info'][bssid][4]
                    wc_title = Gtk.MenuItem("WiFi %s Connected" % wifinum)
                    wc_title.set_sensitive(False)
                    self.menu.append(wc_title)
                    connection_item = Gtk.ImageMenuItem(ssid)
                    connection_item.set_image(self.openwifi(bar))
                    connection_item.show()
                    disconnect_item = Gtk.MenuItem("Disconnect from %s" % ssid)
                    disconnect_item.connect("activate", self.disconnectwifi,
                                            netcard)
                    self.menu.append(connection_item)
                    self.menu.append(disconnect_item)
                    self.wifiListMenu(netcard, bssid, True)
                    diswifi = Gtk.MenuItem("Disable Wifi %s" % wifinum)
                    diswifi.connect("activate", self.disable_Wifi, netcard)
                    self.menu.append(diswifi)
                self.menu.append(Gtk.SeparatorMenuItem())
                wifinum += 1

        if ifWlan() is False and wiredonlineinfo() is False:
            open_item = Gtk.MenuItem("Enable Networking")
            open_item.connect("activate", self.openNetwork)
            self.menu.append(open_item)
        else:
            close_item = Gtk.MenuItem("Disable Networking")
            close_item.connect("activate", self.closeNetwork)
            self.menu.append(close_item)
        close_manager = Gtk.MenuItem("Close Network Manager")
        close_manager.connect("activate", self.stop_manager)
        self.menu.append(close_manager)
        self.menu.show_all()
        return self.menu

    def wifiListMenu(self, wificard, cbssid, passes):
        wiconncmenu = Gtk.Menu()
        avconnmenu = Gtk.MenuItem("Available Connections")
        avconnmenu.set_submenu(wiconncmenu)
        for bssid in self.cardinfo[wificard]['info']:
            ssid = self.cardinfo[wificard]['info'][bssid][0]
            sn = self.cardinfo[wificard]['info'][bssid][4]
            caps = self.cardinfo[wificard]['info'][bssid][6]
            if passes is True:
                if cbssid != bssid:
                    menu_item = Gtk.ImageMenuItem(ssid)
                    if caps == 'E' or caps == 'ES':
                        menu_item.set_image(self.openwifi(sn))
                        menu_item.connect("activate", self.menu_click_open,
                                          ssid, bssid, wificard)
                    else:
                        menu_item.set_image(self.securewifi(sn))
                        menu_item.connect("activate", self.menu_click_lock,
                                          ssid, bssid, wificard)
                    menu_item.show()
                    wiconncmenu.append(menu_item)
            else:
                menu_item = Gtk.ImageMenuItem(ssid)
                if caps == 'E' or caps == 'ES':
                    menu_item.set_image(self.openwifi(sn))
                    menu_item.connect("activate", self.menu_click_open, ssid,
                                      bssid, wificard)
                else:
                    menu_item.set_image(self.securewifi(sn))
                    menu_item.connect("activate", self.menu_click_lock, ssid,
                                      bssid, wificard)
                menu_item.show()
                wiconncmenu.append(menu_item)
        self.menu.append(avconnmenu)

    def menu_click_open(self, widget, ssid, bssid, wificard):
        if bssid in open(wpa_supplican).read():
            connectToSsid(ssid, wificard)
        else:
            Open_Wpa_Supplicant(ssid, bssid, wificard)
        self.updateinfo()
        self.ifruning = False

    def menu_click_lock(self, widget, ssid, bssid, wificard):
        if bssid in open(wpa_supplican).read():
            connectToSsid(ssid, wificard)
        else:
            Authentication(ssid, bssid, wificard)
        self.updateinfo()
        self.ifruning = False

    def disconnectwifi(self, widget, wificard):
        wifiDisconnection(wificard)
        self.updateinfo()
        self.ifruning = False

    def disable_Wifi(self, widget, wificard):
        disableWifi(wificard)
        self.updateinfo()
        self.ifruning = False

    def enable_Wifi(self, widget, wificard):
        enableWifi(wificard)
        self.updateinfo()
        self.ifruning = False

    def connectcard(self, widget, netcard):
        startnetworkcard(netcard)
        self.updateinfo()
        self.ifruning = False

    def disconnectcard(self, widget, netcard):
        stopnetworkcard(netcard)
        self.updateinfo()
        self.ifruning = False

    def restartcardconnection(self, widget, netcard):
        restartnetworkcard(netcard)
        self.updateinfo()
        self.ifruning = False

    def closeNetwork(self, widget):
        stopallnetwork()
        self.updateinfo()
        self.ifruning = False

    def openNetwork(self, widget):
        startallnetwork()
        self.updateinfo()
        self.ifruning = False

    def openwifi(self, bar):
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

    def securewifi(self, bar):
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
        if self.ifruning is False:
            self.ifruning = True
            defaultdev = defaultcard()
            default_type = self.network_type(defaultdev)
            self.cardinfo = networkdictionary()
            sleep(1)
            GLib.idle_add(self.updatetray, defaultdev, default_type)

    def updatetray(self, defaultdev, default_type):
        self.updatetrayicon(defaultdev, default_type)
        self.trayStatus(defaultdev)

    def updatetrayloop(self):
        while True:
            self.checkfornewcard()
            self.updateinfo()
            self.ifruning = False
            sleep(20)

    def network_type(self, defaultdev):
        if defaultdev is None:
            return None
        elif 'wlan' in defaultdev:
            return 'wifi'
        else:
            return 'wire'

    def default_wifi_state(self, defaultdev):
        if self.cardinfo[defaultdev]['state']["connection"] == "Connected":
            bssid = self.cardinfo[defaultdev]['state']["bssid"]
            return self.cardinfo[defaultdev]['info'][bssid][4]
        else:
            return None

    def checkfornewcard(self):
        if os.path.exists("/usr/local/bin/netcardmgr"):
            if isanewnetworkcardinstall() is True:
                os.system("doas netcardmgr")

    def updatetrayicon(self, defaultdev, card_type):
        if card_type is None:
            self.statusIcon.set_from_icon_name('nm-no-connection')
        elif card_type == 'wire':
            self.statusIcon.set_from_icon_name('nm-adhoc')
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
        self.ifruning = False
        self.thr = threading.Thread(target=self.updatetrayloop)
        self.thr.setDaemon(True)
        self.thr.start()
        Gtk.main()
