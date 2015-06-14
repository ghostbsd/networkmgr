#!/usr/local/bin/python

import gtk
import gobject as GObject
import threading
from sys import path
path.append("/usr/local/share/networkmgr")
from time import sleep
from net_api import netstate, ssidliste, barpercent, keyinfo, get_ssid
from net_api import wiredonlineinfo, wiredconnectedinfo, stopwirednetwork
from net_api import startwirednetwork, wifidisconnection, ifWlan, ifStatue
from net_api import stopallnetwork, startallnetwork, connectToSsid
from net_api import ifWlanInRc, disableWifi, enableWifi
from authentication import Authentication, Open_Wpa_Supplicant
import locale
encoding = locale.getpreferredencoding()
utf8conv = lambda x: str(x, encoding).encode('utf8')
threadBreak = False
GObject.threads_init()

wpa_supplican = "/etc/wpa_supplicant.conf"
ncard = 'sh /usr/local/share/networkmgr/detect-nics.sh'
icon_path = '/usr/local/share/networkmgr/icons'
# Icon name
sgnal0 = '%s/nm-signal-00.png' % icon_path
sgnal25 = '%s/nm-signal-25.png' % icon_path
sgnal50 = '%s/nm-signal-50.png' % icon_path
sgnal75 = '%s/nm-signal-75.png' % icon_path
sgnal100 = '%s/nm-signal-100.png' % icon_path
secure0 = '%s/nm-signal-00-secure.png' % icon_path
secure25 = '%s/nm-signal-25-secure.png' % icon_path
secure50 = '%s/nm-signal-50-secure.png' % icon_path
secure75 = '%s/nm-signal-75-secure.png' % icon_path
secure100 = '%s/nm-signal-100-secure.png' % icon_path
wirec = '%s/nm-device-wired.png' % icon_path
wirenc = '%s/nm-no-connection.png' % icon_path


class trayIcon(object):
    def __init__(self):
        self.statusIcon = gtk.StatusIcon()
        # self.statusIcon.set_tooltip('Tracker Desktop Search')
        self.statusIcon.set_visible(True)
        self.menu = gtk.Menu()
        self.menu.show_all()
        self.act = False
        self.statusIcon.connect("activate", self.leftclick)
        self.statusIcon.connect('popup-menu', self.icon_clicked)

    def nm_menu(self):
        self.ssid_name = ssidliste()
        self.menu = gtk.Menu()
        e_title = gtk.MenuItem()
        e_title.set_label("Ethernet Network")
        e_title.set_sensitive(False)
        self.menu.append(e_title)
        if ifWlan() is None and wiredonlineinfo() is None:
            open_item = gtk.MenuItem("Enable Networking")
            open_item.connect("activate", self.openNetwork)
            self.menu.append(open_item)
        else:
            disconnected = gtk.MenuItem()
            if wiredonlineinfo() is True:
                wired_item = gtk.MenuItem("Wire Connected")
                self.menu.append(wired_item)
                disconnect_item = gtk.ImageMenuItem("Disconnect")
                disconnect_item.connect("activate", self.wireddisconnect)
                self.menu.append(disconnect_item)
            elif wiredconnectedinfo() is True:
                disconnected.set_label("Wire Disconnected")
                disconnected.set_sensitive(False)
                self.menu.append(disconnected)
                wired_item = gtk.MenuItem("Connection")
                wired_item.connect("activate", self.wiredconnect)
                self.menu.append(wired_item)
            else:
                disconnected.set_label("Disconnected")
                disconnected.set_sensitive(False)
                self.menu.append(disconnected)
            self.menu.append(gtk.SeparatorMenuItem())
            w_title = gtk.MenuItem()
            if ifWlanInRc()is None:
                pass
            else:
                if ifWlan() is None and ifWlanInRc() is True:
                    w_title.set_label("WiFi Networks")
                    w_title.set_sensitive(False)
                    self.menu.append(w_title)
                    w_title.set_label("WiFi is disabled")
                    w_title.set_sensitive(False)
                    self.menu.append(w_title)
                    self.menu.append(gtk.SeparatorMenuItem())
                elif ifStatue() is None:
                    w_title.set_label("WiFi Networks")
                    w_title.set_sensitive(False)
                    self.menu.append(w_title)
                    w_title.set_label("Disconnected")
                    w_title.set_sensitive(False)
                    self.menu.append(w_title)
                    self.wifiListMenu()
                    self.menu.append(gtk.SeparatorMenuItem())
                else:
                    w_title.set_label("WiFi Networks")
                    w_title.set_sensitive(False)
                    self.menu.append(w_title)
                    bar = barpercent(get_ssid())
                    connection_item = gtk.ImageMenuItem(get_ssid())
                    connection_item.set_image(self.openwifi(bar))
                    connection_item.show()
                    disconnect_item = gtk.MenuItem("Disconnect")
                    disconnect_item.connect("activate",
                                            self.disconnectfromwifi)
                    self.menu.append(connection_item)
                    self.menu.append(disconnect_item)
                    self.menu.append(gtk.SeparatorMenuItem())
                    self.wifiListMenu()
                    self.menu.append(gtk.SeparatorMenuItem())
            close_item = gtk.MenuItem("Disable Networking")
            close_item.connect("activate", self.closeNetwork)
            self.menu.append(close_item)
            if ifWlan() is None and ifWlanInRc() is True:
                enawifi = gtk.MenuItem("Enable Wifi")
                enawifi.connect("activate", self.disable_Wifi)
                self.menu.append(enawifi)
            # elif ifWlan() is True:
            #    diswifi = gtk.MenuItem("Disable Wifi")
            #    diswifi.connect("activate", self.enable_Wifi)
            #    self.menu.append(diswifi)
        self.menu.show_all()
        return self.menu

    def wifiListMenu(self):
        for name in self.ssid_name:
            bar = barpercent(name)
            if ifStatue() is True:
                if get_ssid() == name:
                    pass
                else:
                    menu_item = gtk.ImageMenuItem(name)
                    if keyinfo(name) == 'E':
                        menu_item.set_image(self.openwifi(bar))
                        menu_item.connect("activate", self.menu_click_open,
                                          name)
                    else:
                        menu_item.set_image(self.protectedwifi(bar))
                        menu_item.connect("activate", self.menu_click_look,
                                          name)
                    menu_item.show()
                    self.menu.append(menu_item)
            else:
                menu_item = gtk.ImageMenuItem(name)
                if keyinfo(name) == 'E':
                    menu_item.set_image(self.openwifi(bar))
                    menu_item.connect("activate", self.menu_click_open, name)
                else:
                    menu_item.set_image(self.protectedwifi(bar))
                    menu_item.connect("activate", self.menu_click_look, name)
                menu_item.show()
                self.menu.append(menu_item)

    def menu_click_open(self, widget, name):
        Open_Wpa_Supplicant(name)
        self.check()

    def menu_click_look(self, widget, name):
        if name in open(wpa_supplican).read():
            connectToSsid(name)
            self.check()
        else:
            Authentication(name)
            self.check()

    def disconnectfromwifi(self, widget):
        wifidisconnection()
        self.check()

    def disable_Wifi(self, widget):
        disableWifi()
        self.check()

    def enable_Wifi(self, widget):
        enableWifi()
        self.check

    def wiredconnect(self, widget):
        startwirednetwork()
        self.check()

    def wireddisconnect(self, widget):
        stopwirednetwork()
        self.check()

    def closeNetwork(self, widget):
        stopallnetwork()
        self.check()

    def openNetwork(self, widget):
        startallnetwork()
        self.check()

    def leftclick(self, status_icon):
        button = 1
        position = gtk.status_icon_position_menu
        time = gtk.get_current_event_time()
        self.nm_menu()
        self.menu.popup(None, None, position, button, time, status_icon)

    def icon_clicked(self, status_icon, button, time):
        position = gtk.status_icon_position_menu
        self.nm_menu()
        self.menu.popup(None, None, position, button, time, status_icon)

    def openwifi(self, bar):
        img = gtk.Image()
        if bar > 75:
            img.set_from_file(sgnal100)
        elif bar > 50:
            img.set_from_file(sgnal75)
        elif bar > 25:
            img.set_from_file(sgnal50)
        elif bar > 5:
            img.set_from_file(sgnal25)
        else:
            img.set_from_file(sgnal0)
        img.show()
        return img

    def protectedwifi(self, bar):
        img = gtk.Image()
        if bar > 75:
            img.set_from_file(secure100)
        elif bar > 50:
            img.set_from_file(secure75)
        elif bar > 25:
            img.set_from_file(secure50)
        elif bar > 5:
            img.set_from_file(secure25)
        else:
            img.set_from_file(secure0)
        img.show()
        return img

    def checkloop(self):
        while 1:
            self.check()
            sleep(10)

    def check(self):
        state = netstate()
        if state == 120:
            self.statusIcon.set_from_file(wirec)
        elif state == 110:
            self.statusIcon.set_from_file(wirenc)
        elif state > 75:
            self.statusIcon.set_from_file(sgnal100)
        elif state > 50:
            self.statusIcon.set_from_file(sgnal75)
        elif state > 25:
            self.statusIcon.set_from_file(sgnal50)
        elif state > 5:
            self.statusIcon.set_from_file(sgnal25)
        else:
            self.statusIcon.set_from_file(sgnal0)
        return True

    def tray(self):
        thr = threading.Thread(target=self.checkloop)
        thr.setDaemon(True)
        thr.start()
        gtk.main()
