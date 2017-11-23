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
import threading
from sys import path
import locale
path.append("/usr/local/share/networkmgr")

from time import sleep
from net_api import netstate, barpercent, get_ssid, ifWlanDisable
from net_api import wiredonlineinfo, wiredconnectedinfo, stopwirednetwork
from net_api import startwirednetwork, wifiDisconnection, ifWlan, ifStatue
from net_api import stopallnetwork, startallnetwork, connectToSsid
from net_api import ifWlanInRc, disableWifi, enableWifi, bssidsn
from authentication import Authentication, Open_Wpa_Supplicant
from net_api import wifiListe, scanWifiBssid, conectionStatus
encoding = locale.getpreferredencoding()

threadBreak = False
GObject.threads_init()

wpa_supplican = "/etc/wpa_supplicant.conf"
ncard = 'sh /usr/local/share/networkmgr/detect-nics.sh'

class trayIcon(object):
    def __init__(self):
        self.statusIcon = Gtk.StatusIcon()
        self.statusIcon.set_visible(True)
        self.statusIcon.connect("activate", self.leftclick)
        self.statusIcon.connect('popup-menu', self.icon_clicked)

    def leftclick(self, status_icon):
        if not self.thr.is_alive():
            self.thr.start()
        button = 1
        #position = Gtk.StatusIcon.position_menu()
        time = Gtk.get_current_event_time()
        self.nmMenu.popup(None, None, None, status_icon, button, time)

    def icon_clicked(self, status_icon, button, time):
        if not self.thr.is_alive():
            self.thr.start()
        #position = Gtk.status_icon_position_menu
        # self.nm_menu().popup(None, None, position, button, time, status_icon)
        self.nmMenu.popup(None, None, None, status_icon, button, time)

    def nm_menu(self):
        self.menu = Gtk.Menu()
        e_title = Gtk.MenuItem()
        e_title.set_label("Ethernet Network")
        e_title.set_sensitive(False)
        self.menu.append(e_title)
        if ifWlan() is False and wiredonlineinfo() is False:
            open_item = Gtk.MenuItem("Enable Networking")
            open_item.connect("activate", self.openNetwork)
            self.menu.append(open_item)
        else:
            disconnected = Gtk.MenuItem()
            if wiredonlineinfo() is True:
                wired_item = Gtk.MenuItem("Wire Connected")
                self.menu.append(wired_item)
                disconnect_item = Gtk.ImageMenuItem("Disable")
                disconnect_item.connect("activate", self.wireddisconnect)
                self.menu.append(disconnect_item)
            elif wiredconnectedinfo() is True:
                disconnected.set_label("Wire Disable")
                disconnected.set_sensitive(False)
                self.menu.append(disconnected)
                wired_item = Gtk.MenuItem("Enable")
                wired_item.connect("activate", self.wiredconnect)
                self.menu.append(wired_item)
            else:
                disconnected.set_label("Wire Disconnected")
                disconnected.set_sensitive(False)
                self.menu.append(disconnected)
            self.menu.append(Gtk.SeparatorMenuItem())
            if ifWlanInRc() is False:
                pass
            else:
                if ifWlanDisable() is True and ifWlanInRc() is True:
                    w_title = Gtk.MenuItem()
                    w_title.set_label("WiFi Networks")
                    w_title.set_sensitive(False)
                    self.menu.append(w_title)
                    wd_title = Gtk.MenuItem()
                    wd_title.set_label("WiFi is disabled")
                    wd_title.set_sensitive(False)
                    self.menu.append(wd_title)
                    self.menu.append(Gtk.SeparatorMenuItem())
                elif ifStatue() is False:
                    w_title = Gtk.MenuItem()
                    w_title.set_label("WiFi Networks")
                    w_title.set_sensitive(False)
                    self.menu.append(w_title)
                    d_title = Gtk.MenuItem()
                    d_title.set_label("Disconnected")
                    d_title.set_sensitive(False)
                    self.menu.append(d_title)
                    self.wifiListMenu()
                    self.menu.append(Gtk.SeparatorMenuItem())
                else:
                    w_title = Gtk.MenuItem()
                    w_title.set_label("WiFi Networks")
                    w_title.set_sensitive(False)
                    self.menu.append(w_title)
                    bar = bssidsn(get_ssid())
                    connection_item = Gtk.ImageMenuItem(get_ssid())
                    connection_item.set_image(self.openwifi(bar))
                    connection_item.show()
                    disconnect_item = Gtk.MenuItem("Disconnect")
                    disconnect_item.connect("activate",
                                            self.disconnectfromwifi)
                    self.menu.append(connection_item)
                    self.menu.append(disconnect_item)
                    self.menu.append(Gtk.SeparatorMenuItem())
                    self.wifiListMenu()
            if ifWlanDisable() is True and ifWlanInRc() is True:
                enawifi = Gtk.MenuItem("Enable Wifi")
                enawifi.connect("activate", self.enable_Wifi)
                self.menu.append(enawifi)
            elif ifWlanDisable() is False:
                diswifi = Gtk.MenuItem("Disable Wifi")
                diswifi.connect("activate", self.disable_Wifi)
                self.menu.append(diswifi)
            self.menu.append(Gtk.SeparatorMenuItem())
            close_item = Gtk.MenuItem("Disable Networking")
            close_item.connect("activate", self.closeNetwork)
            self.menu.append(close_item)
        self.menu.show_all()
        return self.menu

    def wifiListMenu(self):
        for wifiData in wifiListe():
            if ifStatue() is True:
                if get_ssid() == wifiData[0]:
                    pass
                else:
                    menu_item = Gtk.ImageMenuItem(wifiData[0])
                    if wifiData[6] == 'E' or wifiData[6] == 'ES':
                        menu_item.set_image(self.openwifi(barpercent(wifiData[4])))
                        menu_item.connect("activate", self.menu_click_open,
                                          wifiData[0], wifiData[1])
                    else:
                        menu_item.set_image(self.securewifi(barpercent(wifiData[4])))
                        menu_item.connect("activate", self.menu_click_lock,
                                          wifiData[0], wifiData[1])
                    menu_item.show()
                    self.menu.append(menu_item)
            else:
                menu_item = Gtk.ImageMenuItem(wifiData[0])
                if wifiData[6] == 'E' or wifiData[6] == 'ES':
                    menu_item.set_image(self.openwifi(barpercent(wifiData[4])))
                    menu_item.connect("activate", self.menu_click_open,
                                      wifiData[0], wifiData[1])
                else:
                    menu_item.set_image(self.securewifi(barpercent(wifiData[4])))
                    menu_item.connect("activate", self.menu_click_lock,
                                      wifiData[0], wifiData[1])
                menu_item.show()
                self.menu.append(menu_item)

    def menu_click_open(self, widget, ssid, bssid):
        Open_Wpa_Supplicant(ssid, bssid)
        if not self.thr.is_alive():
            self.thr.start()
        else:
            self.nmMenu = self.nm_menu()

    def menu_click_lock(self, widget, ssid, bssid):
        if ssid in open(wpa_supplican).read():
            connectToSsid(ssid)
        else:
            Authentication(ssid, bssid)
        if not self.thr.is_alive():
            self.thr.start()
        else:
            self.nmMenu = self.nm_menu()

    def disconnectfromwifi(self, widget):
        wifiDisconnection()
        if not self.thr.is_alive():
            self.thr.start()
        else:
            self.nmMenu = self.nm_menu()

    def disable_Wifi(self, widget):
        disableWifi()
        if not self.thr.is_alive():
            self.thr.start()
        else:
            self.nmMenu = self.nm_menu()

    def enable_Wifi(self, widget):
        enableWifi()
        if not self.thr.is_alive():
            self.thr.start()
        else:
            self.nmMenu = self.nm_menu()

    def wiredconnect(self, widget):
        startwirednetwork()
        if not self.thr.is_alive():
            self.thr.start()
        else:
            self.nmMenu = self.nm_menu()

    def wireddisconnect(self, widget):
        stopwirednetwork()
        if not self.thr.is_alive():
            self.thr.start()
        else:
            self.nmMenu = self.nm_menu()

    def closeNetwork(self, widget):
        stopallnetwork()
        if not self.thr.is_alive():
            self.thr.start()
        else:
            self.nmMenu = self.nm_menu()

    def openNetwork(self, widget):
        startallnetwork()
        if not self.thr.is_alive():
            self.thr.start()
        else:
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

    def update_everything(self):
        self.check()

    def checkloop(self):
        while True:
            #GLib.idle_add(self.update_everything)
            self.nmMenu = self.nm_menu()
            GLib.idle_add(self.update_everything)
            self.trayStatus()
            sleep(20)

    def check(self):
        state = netstate()
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
