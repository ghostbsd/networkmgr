#!/usr/local/bin/python

import gtk
import gobject
from net_api import netstate, ssidliste, barpercent, keyinfo, get_ssid
from net_api import wiredonlineinfo, wiredconnectedinfo, stopwirednetwork
from  net_api import startwirednetwork, wifidisconnection, ifWlan
from net_api import stopallnetwork, startallnetwork
from authentication import Authentication, Open_Wpa_Supplicant
from netcardmgr import autoConfigure
ncard = 'sh /usr/local/share/networkmgr/detect-nics.sh'

icons24 = '/usr/local/share/networkmgr/icons/24/'

sgnal0 = '%snm-signal-00.png' % icons24
sgnal25 = '%snm-signal-25.png' % icons24
sgnal50 = '%snm-signal-50.png' % icons24
sgnal75 = '%snm-signal-75.png' % icons24
sgnal100 = '%snm-signal-100.png' % icons24
secure0 = '%snm-signal-00-secure.png' % icons24
secure25 = '%snm-signal-25-secure.png' % icons24
secure50 = '%snm-signal-50-secure.png' % icons24
secure75 = '%snm-signal-75-secure.png' % icons24
secure100 = '%snm-signal-100-secure.png' % icons24
wirec = '%snm-adhoc.png' % icons24
wirenc = '%snm-no-connection.png' % icons24


class trayIcon(object):
    """
    Use GTK to create an object in the system tray
    and manipulate icon shown if there is an issue.
    """
    def __init__(self):
        self.statusIcon = gtk.StatusIcon()
        #self.statusIcon.set_tooltip('Tracker Desktop Search')
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
            open_item = gtk.MenuItem("Open Networking")
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
            if get_ssid() is None:
                pass
            elif get_ssid() == '""':
                w_title.set_label("Wi-Fi Disconnected")
                w_title.set_sensitive(False)
                self.menu.append(w_title)
                self.wifiListMenu()
                self.menu.append(gtk.SeparatorMenuItem())
            else:
                w_title.set_label("Wi-Fi Connected")
                w_title.set_sensitive(False)
                self.menu.append(w_title)
                bar = barpercent(get_ssid())
                connection_item = gtk.ImageMenuItem(get_ssid())
                connection_item.set_image(self.openwifi(bar))
                connection_item.show()
                disconnect_item = gtk.MenuItem("Disconnect")
                disconnect_item.connect("activate", self.disconnectfromwifi)
                self.menu.append(connection_item)
                self.menu.append(disconnect_item)
                self.menu.append(gtk.SeparatorMenuItem())
                self.wifiListMenu()
            close_item = gtk.MenuItem("Close Networking")
            close_item.connect("activate", self.closeNetwork)
            self.menu.append(close_item)
        self.menu.show_all()
        return self.menu

    def wifiListMenu(self):
        for name in self.ssid_name:
            bar = barpercent(name)
            if get_ssid() == name:
                pass
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

    def menu_click_look(self, widget, name):
        Authentication(name)

    def disconnectfromwifi(self, widget):
        wifidisconnection()

    def wiredconnect(self, widget):
        startwirednetwork()

    def wireddisconnect(self, widget):
        stopwirednetwork()

    def closeNetwork(self, widget):
        stopallnetwork()

    def openNetwork(self, widget):
        startallnetwork()

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

    def check(self):
        state = netstate()
        #print state
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
        elif state is None:
            self.statusIcon.set_from_file(wirenc)
        else:
            self.statusIcon.set_from_file(sgnal0)
        return True

    def tray(self):
        self.check()
        gobject.timeout_add(10000, self.check)
        gtk.main()

autoConfigure()
i = trayIcon()
i.tray()