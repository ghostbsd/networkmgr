#!/usr/local/bin/python
"""
Copyright (c) 2014-2016, GhostBSD. All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

1. Redistribution's of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.

2. Redistribution's in binary form must reproduce the above
   copyright notice,this list of conditions and the following
   disclaimer in the documentation and/or other materials provided
   with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES(INCLUDING,
BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject, GLib
from gi.repository.GdkPixbuf import Pixbuf
from time import sleep
from subprocess import call
import threading
from sys import path
import locale
import os
path.append("/usr/local/share/networkmgr")
from net_api import netstate, barpercent, get_ssid, ifWlanDisable
from net_api import wiredonlineinfo, stopnetworkcard, isanewnetworkcardinstall
from net_api import startnetworkcard, wifiDisconnection, ifWlan, ifStatue
from net_api import stopallnetwork, startallnetwork, connectToSsid
from net_api import ifWlanInRc, disableWifi, enableWifi, bssidsn, wired_list
from authentication import Authentication, Open_Wpa_Supplicant
from net_api import wifiListe, conectionStatus, ifcardisonline, defaultcard
from net_api import ifcardconnected, restartnetworkcard, wlan_list 
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
        self.nmMenu.popup(None, None, Gtk.StatusIcon.position_menu, status_icon, button, time)
        #self.nm_menu().popup(None, None, None, status_icon, button, time)

    def icon_clicked(self, status_icon, button, time):
        if not self.thr.is_alive():
            self.thr.start()
        def position(menu, icon):
            return (Gtk.StatusIcon.position_menu(menu, icon))
        #self.nm_menu().popup(None, None, None, status_icon, button, time)
        self.nmMenu.popup(None, None, Gtk.StatusIcon.position_menu, status_icon, button, time)


    def nm_menu(self):
        self.menu = Gtk.Menu()
        e_title = Gtk.MenuItem()
        e_title.set_label("Ethernet Network")
        e_title.set_sensitive(False)
        self.menu.append(e_title)
        self.menu.append(Gtk.SeparatorMenuItem())
        wiredlist = wired_list()
        wlanlist = wlan_list()
        if len(wiredlist) != 0:
            cardnum = 1
            for netcard in wiredlist:
                if ifcardisonline(netcard) is True:
                    wired_item = Gtk.MenuItem("Wired %s Connected" % cardnum)
                    wired_item.connect("activate", self.restartcardconnection, netcard)
                    self.menu.append(wired_item)
                    disconnect_item = Gtk.ImageMenuItem("Disable")
                    disconnect_item.connect("activate", self.disconnectcard, netcard)
                    self.menu.append(disconnect_item)
                elif ifcardconnected(netcard) is True:
                    notonline = Gtk.MenuItem("Wired %s Disable" % cardnum)
                    notonline.set_sensitive(False)
                    self.menu.append(notonline)
                    wired_item = Gtk.MenuItem("Enable")
                    wired_item.connect("activate", self.connectcard, netcard)
                    self.menu.append(wired_item)
                else:
                    disconnected = Gtk.MenuItem("Wired %s Disconnected" % cardnum)
                    disconnected.set_sensitive(False)
                    self.menu.append(disconnected)
                cardnum += 1
                self.menu.append(Gtk.SeparatorMenuItem())
        if len(wlanlist) != 0:  
            w_title = Gtk.MenuItem()
            w_title.set_label("WiFi Network")
            w_title.set_sensitive(False)
            self.menu.append(w_title)
            self.menu.append(Gtk.SeparatorMenuItem())
            wifinum = 1
            for wificard in wlan_list(): 
                if ifWlanDisable(wificard) is True:
                    wd_title = Gtk.MenuItem()
                    wd_title.set_label("WiFi %s Disabled" % wifinum)
                    wd_title.set_sensitive(False)
                    self.menu.append(wd_title)
                    enawifi = Gtk.MenuItem("Enable Wifi %s" % wifinum)
                    enawifi.connect("activate", self.enable_Wifi, wificard)
                    self.menu.append(enawifi)
                elif ifStatue(wificard) is False:
                    d_title = Gtk.MenuItem()
                    d_title.set_label("WiFi %s Disconnected" % wifinum)
                    d_title.set_sensitive(False)
                    self.menu.append(d_title)
                    self.wifiListMenu(wificard, None, False)
                    diswifi = Gtk.MenuItem("Disable Wifi %s" % wifinum)
                    diswifi.connect("activate", self.disable_Wifi, wificard)
                    self.menu.append(diswifi)
                else:
                    ssid = get_ssid(wificard)
                    wc_title = Gtk.MenuItem("WiFi %s Connected" % wifinum)
                    wc_title.set_sensitive(False)
                    self.menu.append(wc_title)
                    bar = bssidsn(ssid, wificard)
                    connection_item = Gtk.ImageMenuItem(ssid)
                    connection_item.set_image(self.openwifi(bar))
                    connection_item.show()
                    disconnect_item = Gtk.MenuItem("Disconnect from %s" % ssid)
                    disconnect_item.connect("activate", self.disconnectfromwifi,
                                            wificard)
                    self.menu.append(connection_item)
                    self.menu.append(disconnect_item)
                    self.wifiListMenu(wificard, ssid, True)
                    diswifi = Gtk.MenuItem("Disable Wifi %s" % wifinum)
                    diswifi.connect("activate", self.disable_Wifi, wificard)
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

    def wifiListMenu(self, wificard, ssid, passes):
        wiconncmenu = Gtk.Menu()
        avconnmenu = Gtk.MenuItem("Available Connections")
        avconnmenu.set_submenu(wiconncmenu)
        for wifiData in wifiListe(wificard):
            if passes is True:
                if ssid == wifiData[0]:
                    pass
                else:
                    menu_item = Gtk.ImageMenuItem(wifiData[0])
                    if wifiData[6] == 'E' or wifiData[6] == 'ES':
                        menu_item.set_image(self.openwifi(barpercent(wifiData[4])))
                        menu_item.connect("activate", self.menu_click_open,
                                          wifiData[0], wifiData[1], wificard)
                    else:
                        menu_item.set_image(self.securewifi(barpercent(wifiData[4])))
                        menu_item.connect("activate", self.menu_click_lock,
                                          wifiData[0], wifiData[1], wificard)
                    menu_item.show()
                    wiconncmenu.append(menu_item)
                    #self.menu.append(menu_item)
            else:
                menu_item = Gtk.ImageMenuItem(wifiData[0])
                if wifiData[6] == 'E' or wifiData[6] == 'ES':
                    menu_item.set_image(self.openwifi(barpercent(wifiData[4])))
                    menu_item.connect("activate", self.menu_click_open,
                                      wifiData[0], wifiData[1], wificard)
                else:
                    menu_item.set_image(self.securewifi(barpercent(wifiData[4])))
                    menu_item.connect("activate", self.menu_click_lock,
                                      wifiData[0], wifiData[1], wificard)
                menu_item.show()
                wiconncmenu.append(menu_item)
                
        self.menu.append(avconnmenu)

    def menu_click_open(self, widget, ssid, bssid, wificard):
        Open_Wpa_Supplicant(ssid, bssid, wificard)
        sleep(5)
        self.nmMenu = self.nm_menu()

    def menu_click_lock(self, widget, ssid, bssid, wificard):
        if ssid in open(wpa_supplican).read():
            connectToSsid(ssid, wificard)
        else:
            Authentication(ssid, bssid, wificard)
        sleep(5)
        self.nmMenu = self.nm_menu()

    def disconnectfromwifi(self, widget, wificard):
        wifiDisconnection(wificard)
        sleep(5)
        self.nmMenu = self.nm_menu()

    def disable_Wifi(self, widget, wificard):
        disableWifi(wificard)
        sleep(5)
        self.nmMenu = self.nm_menu()

    def enable_Wifi(self, widget, wificard):
        enableWifi(wificard)
        sleep(5)
        self.nmMenu = self.nm_menu()

    def connectcard(self, widget, netcard):
        startnetworkcard(netcard)
        sleep(5)
        self.nmMenu = self.nm_menu()

    def disconnectcard(self, widget, netcard):
        stopnetworkcard(netcard)
        sleep(5)
        self.nmMenu = self.nm_menu()

    def restartcardconnection(self, widget, netcard):
        restartnetworkcard(netcard)
        sleep(5)
        self.nmMenu = self.nm_menu()

    def closeNetwork(self, widget):
        stopallnetwork()
        sleep(5)
        self.nmMenu = self.nm_menu()

    def openNetwork(self, widget):
        startallnetwork()
        sleep(5)
        self.nmMenu = self.nm_menu()

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

    def update_everything(self, defaultdev):
        self.check(defaultdev)

    def checkloop(self):
        while True:
            defaultdev = defaultcard()
            self.nmMenu = self.nm_menu()
            GLib.idle_add(self.update_everything, defaultdev)
            #self.trayStatus()
            sleep(20)
            self.checkfornewcard()

    def checkfornewcard(self):
        if os.path.exists("/usr/local/bin/netcardmgr"):
            if isanewnetworkcardinstall() is True:
                call("doas netcardmgr", shell=True)

    def check(self, defaultdev):
        state = netstate(defaultdev)
        if state == 200:
            self.statusIcon.set_from_icon_name('nm-adhoc')
        elif state is None:
            self.statusIcon.set_from_icon_name('nm-no-connection')
        elif state > 75:
            self.statusIcon.set_from_icon_name('nm-signal-100')
        elif state > 50:
            self.statusIcon.set_from_icon_name('nm-signal-75')
        elif state > 25:
            self.statusIcon.set_from_icon_name('nm-signal-50')
        elif state > 5:
            self.statusIcon.set_from_icon_name('nm-signal-25')
        else:
            self.statusIcon.set_from_icon_name('nm-signal-00')
        return True

    def trayStatus(self):
        self.statusIcon.set_tooltip_text("%s" % conectionStatus())

    def tray(self):
        self.thr = threading.Thread(target=self.checkloop)
        self.thr.setDaemon(True)
        self.thr.start()
        Gtk.main()
