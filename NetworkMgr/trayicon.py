#!/usr/bin/env python

import gi
gi.require_version('Gtk', '3.0')
import gettext
import threading
import _thread
import locale
from time import sleep
from gi.repository import Gtk, GObject, GLib
from NetworkMgr.net_api import (
    stopnetworkcard,
    startnetworkcard,
    wifiDisconnection,
    restart_all_nics,
    stopallnetwork,
    startallnetwork,
    connectToSsid,
    disableWifi,
    enableWifi,
    connectionStatus,
    networkdictionary,
    delete_ssid_wpa_supplicant_config,
    nic_status,
    EAP_METHODS,
    PHASE2_METHODS,
    DEFAULT_CA_CERT,
    is_enterprise_network,
    get_security_type,
    validate_certificate,
    get_system_ca_certificates,
    write_eap_config
)
from NetworkMgr.configuration import network_card_configuration

from NetworkMgr.wg_api import (
    wg_dictionary,
    disable_wg,
    enable_wg,
    wg_status
)

gettext.bindtextdomain('networkmgr', '/usr/local/share/locale')
gettext.textdomain('networkmgr')
_ = gettext.gettext

encoding = locale.getpreferredencoding()
threadBreak = False
GObject.threads_init()


class trayIcon(object):

    def stop_manager(self, widget):
        Gtk.main_quit()

    def __init__(self):
        self.if_running = False
        self.cardinfo = None
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
        if len(self.wginfo['configs'])> 0 and self.wginfo['service'] == '"NO"':
            wg_title = Gtk.MenuItem()
            wg_title.set_label(_("WireGuard VPN"))
            wg_title.set_sensitive(False)
            self.menu.append(wg_title)
            self.menu.append(Gtk.SeparatorMenuItem())
            wg_devices = self.wginfo['configs']
            for wg_dev in wg_devices:
                connection_state = wg_devices[wg_dev]['state']
                connection_info = wg_devices[wg_dev]['info']
                if connection_state == "Connected":
                    wg_item = Gtk.MenuItem(_("%s Connected") % connection_info)
                    wg_item.set_sensitive(False)
                    self.menu.append(wg_item)
                    disconnectwg_item = Gtk.ImageMenuItem(_(f"Disable {wg_dev}"))
                    disconnectwg_item.connect("activate", self.disconnectWG, wg_dev)
                    self.menu.append(disconnectwg_item)
                else:
                    notonlinewg = Gtk.MenuItem(_("%s Disconnected") % connection_info)
                    notonlinewg.set_sensitive(False)
                    self.menu.append(notonlinewg)
                    wiredwg_item = Gtk.MenuItem(_("Enable"))
                    wiredwg_item.connect("activate", self.connectWG, wg_dev)
                    self.menu.append(wiredwg_item)
            self.menu.append(Gtk.SeparatorMenuItem())

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
            if "wlan" not in netcard:
                if connection_state == "Connected":
                    wired_item = Gtk.MenuItem(_("Wired %s Connected") % cardnum)
                    wired_item.set_sensitive(False)
                    self.menu.append(wired_item)
                    disconnect_item = Gtk.ImageMenuItem(_(f"Disable {netcard}"))
                    disconnect_item.connect("activate", self.disconnectcard,
                                            netcard)
                    self.menu.append(disconnect_item)
                    configure_item = Gtk.ImageMenuItem(f"Configure {netcard}")
                    configure_item.connect("activate", self.configuration_window_open, netcard)
                    self.menu.append(configure_item)
                elif connection_state == "Disconnected":
                    notonline = Gtk.MenuItem(_("Wired %s Disconnected") % cardnum)
                    notonline.set_sensitive(False)
                    self.menu.append(notonline)
                    wired_item = Gtk.MenuItem(_("Enable"))
                    wired_item.connect("activate", self.connectcard, netcard)
                    self.menu.append(wired_item)
                else:
                    disconnected = Gtk.MenuItem(_("Wired %s Unplug") % cardnum)
                    disconnected.set_sensitive(False)
                    self.menu.append(disconnected)
                cardnum += 1
                self.menu.append(Gtk.SeparatorMenuItem())
            elif "wlan" in netcard:
                if connection_state == "Disabled":
                    wd_title = Gtk.MenuItem()
                    wd_title.set_label(_("WiFi %s Disabled") % wifinum)
                    wd_title.set_sensitive(False)
                    self.menu.append(wd_title)
                    enawifi = Gtk.MenuItem(_("Enable Wifi %s") % wifinum)
                    enawifi.connect("activate", self.enable_Wifi, netcard)
                    self.menu.append(enawifi)
                elif connection_state == "Disconnected":
                    d_title = Gtk.MenuItem()
                    d_title.set_label(_("WiFi %s Disconnected") % wifinum)
                    d_title.set_sensitive(False)
                    self.menu.append(d_title)
                    self.wifiListMenu(netcard, None, False, cards)
                    diswifi = Gtk.MenuItem(_("Disable Wifi %s") % wifinum)
                    diswifi.connect("activate", self.disable_Wifi, netcard)
                    self.menu.append(diswifi)
                else:
                    ssid = cards[netcard]['state']["ssid"]
                    bar = cards[netcard]['info'][ssid][4]
                    wc_title = Gtk.MenuItem(_("WiFi %s Connected") % wifinum)
                    wc_title.set_sensitive(False)
                    self.menu.append(wc_title)
                    connection_item = Gtk.ImageMenuItem(ssid)
                    connection_item.set_image(self.wifi_signal_icon(bar))
                    connection_item.show()
                    disconnect_item = Gtk.MenuItem(_("Disconnect from %s") % ssid)
                    disconnect_item.connect("activate", self.disconnect_wifi,
                                            netcard)
                    self.menu.append(connection_item)
                    self.menu.append(disconnect_item)
                    self.wifiListMenu(netcard, ssid, True, cards)
                    diswifi = Gtk.MenuItem(_("Disable Wifi %s") % wifinum)
                    diswifi.connect("activate", self.disable_Wifi, netcard)
                    self.menu.append(diswifi)
                    configure_item = Gtk.ImageMenuItem(f"Configure {netcard}")
                    configure_item.connect("activate", self.configuration_window_open, netcard)
                    self.menu.append(configure_item)
                self.menu.append(Gtk.SeparatorMenuItem())
                wifinum += 1

        open_item = Gtk.MenuItem(_("Restart Networking"))
        open_item.connect("activate", restart_all_nics)
        self.menu.append(open_item)
        close_manager = Gtk.MenuItem(_("Close Network Manager"))
        close_manager.connect("activate", self.stop_manager)
        self.menu.append(close_manager)
        self.menu.show_all()
        return self.menu

    def ssid_menu_item(self, sn, caps, ssid, ssid_info, wificard):
        menu_item = Gtk.ImageMenuItem(ssid)
        # Check if enterprise network (index 9 contains enterprise flag boolean)
        is_enterprise = len(ssid_info) > 9 and ssid_info[9] is True
        if caps in ('E', 'ES'):
            is_secure = False
            click_action = self.menu_click_open
            ssid_type = ssid
        elif is_enterprise:
            is_secure = True
            click_action = self.menu_click_enterprise
            ssid_type = ssid_info
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
                    menu_item = self.ssid_menu_item(sn, caps, ssid, ssid_info, wificard)
                    wiconncmenu.append(menu_item)
            else:
                menu_item = self.ssid_menu_item(sn, caps, ssid, ssid_info, wificard)
                wiconncmenu.append(menu_item)
        self.menu.append(avconnmenu)

    def configuration_window_open(self, widget, interface):
        network_card_configuration(interface)

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

    def menu_click_enterprise(self, widget, ssid_info, wificard):
        if f'"{ssid_info[0]}"' in open('/etc/wpa_supplicant.conf').read():
            connectToSsid(ssid_info[0], wificard)
        else:
            self.EnterpriseAuthentication(ssid_info, wificard, False)
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

    def connectWG(self, widget, wginfo):
        enable_wg(wginfo)
        self.updateinfo()

    def disconnectWG(self, widget, wginfo):
        disable_wg(wginfo)
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
            self.wginfo = wg_dictionary()
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
        self.statusIcon.set_tooltip_text(connectionStatus(defaultdev, self.cardinfo))

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
            for _ in list(range(60)):
                if nic_status(card) == 'associated':
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
        # Determine caps string - handle extended ssid_info format
        caps_string = ssid_info[-1] if len(ssid_info) <= 7 else ssid_info[6]
        if 'RSN' in caps_string:
            # /etc/wpa_supplicant.conf written by networkmgr
            ws = '\nnetwork={'
            ws += f'\n ssid="{ssid}"'
            ws += '\n key_mgmt=WPA-PSK'
            ws += '\n proto=RSN'
            ws += f'\n psk="{pwd}"\n'
            ws += '}\n'
        elif 'WPA' in caps_string:
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
        import os
        old_umask = os.umask(0o077)
        try:
            with open("/etc/wpa_supplicant.conf", 'a') as wsf:
                wsf.write(ws)
        finally:
            os.umask(old_umask)

    def Open_Wpa_Supplicant(self, ssid, card):
        ws = '\nnetwork={'
        ws += f'\n ssid="{ssid}"'
        ws += '\n key_mgmt=NONE\n}\n'
        import os
        old_umask = os.umask(0o077)
        try:
            with open("/etc/wpa_supplicant.conf", 'a') as wsf:
                wsf.write(ws)
        finally:
            os.umask(old_umask)

    def add_enterprise_to_wpa_supplicant(self, widget, ssid_info, card):
        """Handle enterprise authentication form submission."""
        eap_config = {
            'eap_method': self.eap_method_combo.get_active_text(),
            'identity': self.identity_entry.get_text(),
            'password': self.eap_password.get_text(),
            'phase2': self.phase2_combo.get_active_text() if hasattr(self, 'phase2_combo') else 'MSCHAPV2',
            'anonymous_identity': self.anon_identity_entry.get_text() if hasattr(self, 'anon_identity_entry') else '',
        }

        # Get CA certificate path
        if hasattr(self, 'ca_cert_chooser'):
            ca_file = self.ca_cert_chooser.get_filename()
            if ca_file:
                eap_config['ca_cert'] = ca_file

        # For TLS, get client certificate and key
        if eap_config['eap_method'] == 'TLS':
            if hasattr(self, 'client_cert_chooser'):
                client_cert = self.client_cert_chooser.get_filename()
                if client_cert:
                    eap_config['client_cert'] = client_cert
            if hasattr(self, 'private_key_chooser'):
                private_key = self.private_key_chooser.get_filename()
                if private_key:
                    eap_config['private_key'] = private_key
            if hasattr(self, 'private_key_passwd'):
                eap_config['private_key_passwd'] = self.private_key_passwd.get_text()

        write_eap_config(ssid_info[0], eap_config)
        _thread.start_new_thread(
            self.try_to_connect_to_ssid,
            (ssid_info[0], ssid_info, card)
        )
        self.eap_window.hide()

    def on_eap_method_changed(self, combo):
        """Update dialog fields based on selected EAP method."""
        method = combo.get_active_text()

        # Show/hide TLS-specific fields
        tls_mode = method == 'TLS'
        if hasattr(self, 'client_cert_box'):
            self.client_cert_box.set_visible(tls_mode)
        if hasattr(self, 'private_key_box'):
            self.private_key_box.set_visible(tls_mode)
        if hasattr(self, 'private_key_passwd_box'):
            self.private_key_passwd_box.set_visible(tls_mode)

        # Show/hide password field (not needed for TLS)
        if hasattr(self, 'password_box'):
            self.password_box.set_visible(not tls_mode)

        # Show/hide phase2 (only for PEAP/TTLS)
        if hasattr(self, 'phase2_box'):
            self.phase2_box.set_visible(method in ('PEAP', 'TTLS'))

    def close_eap_window(self, widget):
        self.eap_window.hide()

    def on_eap_password_check(self, widget):
        self.eap_password.set_visibility(widget.get_active())

    def EnterpriseAuthentication(self, ssid_info, card, failed):
        """Create authentication dialog for WPA-Enterprise networks."""
        self.eap_window = Gtk.Window()
        self.eap_window.set_title(_("Enterprise Wi-Fi Authentication"))
        self.eap_window.set_border_width(10)
        self.eap_window.set_size_request(550, 450)

        main_box = Gtk.VBox(spacing=10)
        self.eap_window.add(main_box)

        # Title
        if failed:
            title_text = _(f"{ssid_info[0]} Enterprise Authentication Failed")
        else:
            title_text = _(f"Enterprise Authentication for {ssid_info[0]}")
        title_label = Gtk.Label()
        title_label.set_markup(f"<b><span size='large'>{title_text}</span></b>")
        main_box.pack_start(title_label, False, False, 5)

        # Security info
        security_type = ssid_info[7] if len(ssid_info) > 7 else "WPA2-EAP"
        security_label = Gtk.Label(_(f"Security: {security_type}"))
        main_box.pack_start(security_label, False, False, 0)

        # Grid for form fields
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(8)
        main_box.pack_start(grid, True, True, 5)

        row = 0

        # EAP Method
        eap_label = Gtk.Label(_("EAP Method:"))
        eap_label.set_halign(Gtk.Align.END)
        grid.attach(eap_label, 0, row, 1, 1)
        self.eap_method_combo = Gtk.ComboBoxText()
        for method in EAP_METHODS:
            self.eap_method_combo.append_text(method)
        self.eap_method_combo.set_active(0)  # Default to PEAP
        self.eap_method_combo.connect("changed", self.on_eap_method_changed)
        grid.attach(self.eap_method_combo, 1, row, 2, 1)
        row += 1

        # Phase 2 Authentication (inner method)
        self.phase2_box = Gtk.HBox(spacing=5)
        phase2_label = Gtk.Label(_("Inner Auth:"))
        phase2_label.set_halign(Gtk.Align.END)
        grid.attach(phase2_label, 0, row, 1, 1)
        self.phase2_combo = Gtk.ComboBoxText()
        for method in PHASE2_METHODS:
            self.phase2_combo.append_text(method)
        self.phase2_combo.set_active(0)  # Default to MSCHAPV2
        self.phase2_box.pack_start(self.phase2_combo, True, True, 0)
        grid.attach(self.phase2_box, 1, row, 2, 1)
        row += 1

        # Identity (Username)
        identity_label = Gtk.Label(_("Username:"))
        identity_label.set_halign(Gtk.Align.END)
        grid.attach(identity_label, 0, row, 1, 1)
        self.identity_entry = Gtk.Entry()
        self.identity_entry.set_hexpand(True)
        grid.attach(self.identity_entry, 1, row, 2, 1)
        row += 1

        # Anonymous Identity (optional)
        anon_label = Gtk.Label(_("Anonymous ID:"))
        anon_label.set_halign(Gtk.Align.END)
        grid.attach(anon_label, 0, row, 1, 1)
        self.anon_identity_entry = Gtk.Entry()
        self.anon_identity_entry.set_placeholder_text(_("Optional - for privacy"))
        grid.attach(self.anon_identity_entry, 1, row, 2, 1)
        row += 1

        # Password
        self.password_box = Gtk.VBox()
        pwd_label = Gtk.Label(_("Password:"))
        pwd_label.set_halign(Gtk.Align.END)
        grid.attach(pwd_label, 0, row, 1, 1)
        pwd_hbox = Gtk.HBox(spacing=5)
        self.eap_password = Gtk.Entry()
        self.eap_password.set_visibility(False)
        self.eap_password.set_hexpand(True)
        pwd_hbox.pack_start(self.eap_password, True, True, 0)
        show_pwd_check = Gtk.CheckButton(_("Show"))
        show_pwd_check.connect("toggled", self.on_eap_password_check)
        pwd_hbox.pack_start(show_pwd_check, False, False, 0)
        self.password_box.pack_start(pwd_hbox, True, True, 0)
        grid.attach(self.password_box, 1, row, 2, 1)
        row += 1

        # CA Certificate
        ca_label = Gtk.Label(_("CA Certificate:"))
        ca_label.set_halign(Gtk.Align.END)
        grid.attach(ca_label, 0, row, 1, 1)
        ca_hbox = Gtk.HBox(spacing=5)
        self.ca_cert_chooser = Gtk.FileChooserButton(
            title=_("Select CA Certificate"),
            action=Gtk.FileChooserAction.OPEN
        )
        # Set default CA if available
        system_cas = get_system_ca_certificates()
        if system_cas:
            self.ca_cert_chooser.set_filename(system_cas[0])
        ca_filter = Gtk.FileFilter()
        ca_filter.set_name(_("Certificates (*.pem, *.crt, *.cer)"))
        ca_filter.add_pattern("*.pem")
        ca_filter.add_pattern("*.crt")
        ca_filter.add_pattern("*.cer")
        self.ca_cert_chooser.add_filter(ca_filter)
        ca_hbox.pack_start(self.ca_cert_chooser, True, True, 0)
        grid.attach(ca_hbox, 1, row, 2, 1)
        row += 1

        # TLS-specific fields (hidden by default)
        # Client Certificate
        self.client_cert_box = Gtk.HBox(spacing=5)
        client_cert_label = Gtk.Label(_("Client Cert:"))
        client_cert_label.set_halign(Gtk.Align.END)
        grid.attach(client_cert_label, 0, row, 1, 1)
        self.client_cert_chooser = Gtk.FileChooserButton(
            title=_("Select Client Certificate"),
            action=Gtk.FileChooserAction.OPEN
        )
        self.client_cert_chooser.add_filter(ca_filter)
        self.client_cert_box.pack_start(self.client_cert_chooser, True, True, 0)
        grid.attach(self.client_cert_box, 1, row, 2, 1)
        self.client_cert_box.set_visible(False)
        row += 1

        # Private Key
        self.private_key_box = Gtk.HBox(spacing=5)
        key_label = Gtk.Label(_("Private Key:"))
        key_label.set_halign(Gtk.Align.END)
        grid.attach(key_label, 0, row, 1, 1)
        self.private_key_chooser = Gtk.FileChooserButton(
            title=_("Select Private Key"),
            action=Gtk.FileChooserAction.OPEN
        )
        key_filter = Gtk.FileFilter()
        key_filter.set_name(_("Key files (*.pem, *.key, *.p12)"))
        key_filter.add_pattern("*.pem")
        key_filter.add_pattern("*.key")
        key_filter.add_pattern("*.p12")
        self.private_key_chooser.add_filter(key_filter)
        self.private_key_box.pack_start(self.private_key_chooser, True, True, 0)
        grid.attach(self.private_key_box, 1, row, 2, 1)
        self.private_key_box.set_visible(False)
        row += 1

        # Private Key Password
        self.private_key_passwd_box = Gtk.HBox(spacing=5)
        key_pwd_label = Gtk.Label(_("Key Password:"))
        key_pwd_label.set_halign(Gtk.Align.END)
        grid.attach(key_pwd_label, 0, row, 1, 1)
        self.private_key_passwd = Gtk.Entry()
        self.private_key_passwd.set_visibility(False)
        self.private_key_passwd_box.pack_start(self.private_key_passwd, True, True, 0)
        grid.attach(self.private_key_passwd_box, 1, row, 2, 1)
        self.private_key_passwd_box.set_visible(False)
        row += 1

        # Buttons
        button_box = Gtk.HBox(spacing=10)
        button_box.set_halign(Gtk.Align.END)
        main_box.pack_start(button_box, False, False, 5)

        cancel_btn = Gtk.Button(stock=Gtk.STOCK_CANCEL)
        cancel_btn.connect("clicked", self.close_eap_window)
        button_box.pack_start(cancel_btn, False, False, 0)

        connect_btn = Gtk.Button(stock=Gtk.STOCK_CONNECT)
        connect_btn.connect("clicked", self.add_enterprise_to_wpa_supplicant, ssid_info, card)
        button_box.pack_start(connect_btn, False, False, 0)

        self.eap_window.show_all()
        # Trigger visibility update
        self.on_eap_method_changed(self.eap_method_combo)
        return 'Done'
