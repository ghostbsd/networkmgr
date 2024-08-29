#!/usr/bin/env python

import _thread
import gettext
import locale
import threading
from time import sleep

from gi.repository import Gtk, GObject, GLib

from NetworkMgr.configuration import network_card_configuration
from NetworkMgr.net_api import (
    stop_network_card,
    start_network_card,
    wifi_disconnection,
    restart_all_nics,
    stop_all_network,
    start_all_network,
    connect_to_ssid,
    disable_wifi,
    enable_wifi,
    connection_status,
    network_dictionary,
    delete_ssid_wpa_supplicant_config,
    nic_status
)

gettext.bindtextdomain('networkmgr', '/usr/local/share/locale')
gettext.textdomain('networkmgr')
_ = gettext.gettext

encoding = locale.getpreferredencoding()
threadBreak = False
GObject.threads_init()


class TrayIcon(object):

    def stop_manager(self, widget):
        Gtk.main_quit()

    def __init__(self):
        self.thr = None
        self.password = None
        self.menu = None
        self.window = None
        self.if_running = False
        self.card_info = None
        self.statusIcon = Gtk.StatusIcon()
        self.statusIcon.set_visible(True)
        self.statusIcon.connect("activate", self.left_click)
        self.statusIcon.connect('popup-menu', self.icon_clicked)

    def left_click(self, status_icon):
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
        card_num = 1
        wifi_num = 1
        cards = self.card_info['cards']
        for net_card in cards:
            connection_state = cards[net_card]['state']["connection"]
            if "wlan" not in net_card:
                if connection_state == "Connected":
                    wired_item = Gtk.MenuItem(_("Wired %s Connected") % card_num)
                    wired_item.set_sensitive(False)
                    self.menu.append(wired_item)
                    disconnect_item = Gtk.ImageMenuItem(_(f"Disable {net_card}"))
                    disconnect_item.connect("activate", self.disconnect_card, net_card)
                    self.menu.append(disconnect_item)
                    configure_item = Gtk.ImageMenuItem(f"Configure {net_card}")
                    configure_item.connect("activate", self.configuration_window_open, net_card)
                    self.menu.append(configure_item)
                elif connection_state == "Disconnected":
                    not_online = Gtk.MenuItem(_("Wired %s Disconnected") % card_num)
                    not_online.set_sensitive(False)
                    self.menu.append(not_online)
                    wired_item = Gtk.MenuItem(_("Enable"))
                    wired_item.connect("activate", self.connect_card, net_card)
                    self.menu.append(wired_item)
                else:
                    disconnected = Gtk.MenuItem(_("Wired %s Unplug") % card_num)
                    disconnected.set_sensitive(False)
                    self.menu.append(disconnected)
                card_num += 1
                self.menu.append(Gtk.SeparatorMenuItem())
            elif "wlan" in net_card:
                if connection_state == "Disabled":
                    wd_title = Gtk.MenuItem()
                    wd_title.set_label(_("WiFi %s Disabled") % wifi_num)
                    wd_title.set_sensitive(False)
                    self.menu.append(wd_title)
                    ena_wifi = Gtk.MenuItem(_("Enable Wifi %s") % wifi_num)
                    ena_wifi.connect("activate", self.enable_wifi, net_card)
                    self.menu.append(ena_wifi)
                elif connection_state == "Disconnected":
                    d_title = Gtk.MenuItem()
                    d_title.set_label(_("WiFi %s Disconnected") % wifi_num)
                    d_title.set_sensitive(False)
                    self.menu.append(d_title)
                    self.wifi_list_menu(net_card, None, False, cards)
                    dis_wifi = Gtk.MenuItem(_("Disable Wifi %s") % wifi_num)
                    dis_wifi.connect("activate", self.disable_wifi, net_card)
                    self.menu.append(dis_wifi)
                else:
                    ssid = cards[net_card]['state']["ssid"]
                    bar = cards[net_card]['info'][ssid][4]
                    wc_title = Gtk.MenuItem(_("WiFi %s Connected") % wifi_num)
                    wc_title.set_sensitive(False)
                    self.menu.append(wc_title)
                    connection_item = Gtk.ImageMenuItem(ssid)
                    connection_item.set_image(self.wifi_signal_icon(bar))
                    connection_item.show()
                    disconnect_item = Gtk.MenuItem(_("Disconnect from %s") % ssid)
                    disconnect_item.connect("activate", self.disconnect_wifi, net_card)
                    self.menu.append(connection_item)
                    self.menu.append(disconnect_item)
                    self.wifi_list_menu(net_card, ssid, True, cards)
                    dis_wifi = Gtk.MenuItem(_("Disable Wifi %s") % wifi_num)
                    dis_wifi.connect("activate", self.disable_wifi, net_card)
                    self.menu.append(dis_wifi)
                    configure_item = Gtk.ImageMenuItem(f"Configure {net_card}")
                    configure_item.connect("activate", self.configuration_window_open, net_card)
                    self.menu.append(configure_item)
                self.menu.append(Gtk.SeparatorMenuItem())
                wifi_num += 1

        open_item = Gtk.MenuItem(_("Restart Networking"))
        open_item.connect("activate", restart_all_nics)
        self.menu.append(open_item)
        close_manager = Gtk.MenuItem(_("Close Network Manager"))
        close_manager.connect("activate", self.stop_manager)
        self.menu.append(close_manager)
        self.menu.show_all()
        return self.menu

    def ssid_menu_item(self, sn, caps, ssid, ssid_info, wifi_card):
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
        menu_item.connect("activate", click_action, ssid_type, wifi_card)
        menu_item.show()
        return menu_item

    def wifi_list_menu(self, wifi_card, css_id, passes, cards):
        wiconncmenu = Gtk.Menu()
        avconnmenu = Gtk.MenuItem(_("Available Connections"))
        avconnmenu.set_submenu(wiconncmenu)
        for ssid in cards[wifi_card]['info']:
            ssid_info = cards[wifi_card]['info'][ssid]
            ssid = cards[wifi_card]['info'][ssid][0]
            sn = cards[wifi_card]['info'][ssid][4]
            caps = cards[wifi_card]['info'][ssid][6]
            if passes:
                if css_id != ssid:
                    menu_item = self.ssid_menu_item(sn, caps, ssid, ssid_info, wifi_card)
                    wiconncmenu.append(menu_item)
            else:
                menu_item = self.ssid_menu_item(sn, caps, ssid, ssid_info, wifi_card)
                wiconncmenu.append(menu_item)
        self.menu.append(avconnmenu)

    def configuration_window_open(self, widget, interface):
        network_card_configuration(interface)

    def menu_click_open(self, widget, ssid, wifi_card):
        if f'"{ssid}"' in open("/etc/wpa_supplicant.conf").read():
            connect_to_ssid(ssid, wifi_card)
        else:
            self.open_wpa_supplicant(ssid, wifi_card)
        self.update_info()

    def menu_click_lock(self, widget, ssid_info, wifi_card):
        if f'"{ssid_info[0]}"' in open('/etc/wpa_supplicant.conf').read():
            connect_to_ssid(ssid_info[0], wifi_card)
        else:
            self.authentication(ssid_info, wifi_card, False)
        self.update_info()

    def disconnect_wifi(self, widget, wifi_card):
        wifi_disconnection(wifi_card)
        self.update_info()

    def disable_wifi(self, widget, wifi_card):
        disable_wifi(wifi_card)
        self.update_info()

    def enable_wifi(self, widget, wifi_card):
        enable_wifi(wifi_card)
        self.update_info()

    def connect_card(self, widget, net_card):
        start_network_card(net_card)
        self.update_info()

    def disconnect_card(self, widget, net_card):
        stop_network_card(net_card)
        self.update_info()

    def close_network(self, widget):
        stop_all_network()
        self.update_info()

    def open_network(self, widget):
        start_all_network()
        self.update_info()

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

    def update_info(self):
        if not self.if_running:
            self.if_running = True
            self.card_info = network_dictionary()
            default_card = self.card_info['default']
            default_type = self.network_type(default_card)
            GLib.idle_add(self.update_tray, default_card, default_type)
            self.if_running = False

    def update_tray(self, default_dev, default_type):
        self.update_tray_icon(default_dev, default_type)
        self.tray_status(default_dev)

    def update_tray_loop(self):
        while True:
            self.update_info()
            sleep(20)

    def network_type(self, default_dev):
        if default_dev is None:
            return None
        elif 'wlan' in default_dev:
            return 'wifi'
        else:
            return 'wire'

    def default_wifi_state(self, default_dev):
        info = self.card_info['cards'][default_dev]
        if info['state']["connection"] == "Connected":
            ssid = info['state']["ssid"]
            return info['info'][ssid][4]
        else:
            return None

    def update_tray_icon(self, default_dev, card_type):
        if card_type is None:
            icon_name = 'nm-no-connection'
        elif card_type == 'wire':
            icon_name = 'nm-device-wired'
        else:
            wifi_state = self.default_wifi_state(default_dev)
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

    def tray_status(self, default_dev):
        self.statusIcon.set_tooltip_text(connection_status(default_dev, self.card_info))

    def tray(self):
        self.if_running = False
        self.thr = threading.Thread(target=self.update_tray_loop)
        self.thr.setDaemon(True)
        self.thr.start()
        Gtk.main()

    def close(self, widget):
        self.window.hide()

    def add_to_wpa_supplicant(self, widget, ssid_info, card):
        pwd = self.password.get_text()
        self.setup_wpa_supplicant(ssid_info[0], ssid_info, pwd)
        _thread.start_new_thread(
            self.try_to_connect_to_ssid,
            (ssid_info[0], ssid_info, card)
        )
        self.window.hide()

    def try_to_connect_to_ssid(self, ssid, ssid_info, card):
        if not connect_to_ssid(ssid, card):
            delete_ssid_wpa_supplicant_config(ssid)
            GLib.idle_add(self.restart_authentication, ssid_info, card)
        else:
            for _ in list(range(60)):
                if nic_status(card) == 'associated':
                    self.update_info()
                    break
                sleep(1)
            else:
                delete_ssid_wpa_supplicant_config(ssid)
                GLib.idle_add(self.restart_authentication, ssid_info, card)
        return

    def restart_authentication(self, ssid_info, card):
        self.authentication(ssid_info, card, True)

    def on_check(self, widget):
        self.password.set_visibility(widget.get_active())

    def authentication(self, ssid_info, card, failed):
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

    def setup_wpa_supplicant(self, ssid, ssid_info, pwd):
        if 'RSN' in ssid_info[-1]:
            security = 'WPA-PSK'
            proto = 'RSN'
            psk_line = f'\n psk="{pwd}"\n'
        elif 'WPA' in ssid_info[-1]:
            security = 'WPA-PSK'
            proto = 'WPA'
            psk_line = f'\n psk="{pwd}"\n'
        else:
            security = 'NONE'
            proto = ''
            psk_line = f'\n wep_tx_keyidx=0\n wep_key0={pwd}\n'

        config_lines = f'\nnetwork={{\n ssid="{ssid}"\n key_mgmt={security}\n proto={proto}{psk_line}}}\n'

        with open("/etc/wpa_supplicant.conf", 'a') as wsf:
            wsf.write(config_lines)

    def open_wpa_supplicant(self, ssid, card):
        config_lines = f'\nnetwork={{\n ssid="{ssid}"\n key_mgmt=NONE\n}}\n'
        with open("/etc/wpa_supplicant.conf", 'a') as wsf:
            wsf.write(config_lines)
