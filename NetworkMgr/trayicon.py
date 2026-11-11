#!/usr/bin/env python

"""The NetworkMgr tray icon and its menu.

Owns everything the user sees from the system tray: the interface and
network menus, the passphrase and enterprise credential dialogs, the signal
icons, and the background thread that refreshes all of it. Every system
call it makes goes through NetworkMgr.net_api or NetworkMgr.wg_api.
"""

import gettext
import threading
import _thread
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, GLib, Pango
from time import sleep
from NetworkMgr.net_api import (
    stop_network_card,
    start_network_card,
    disconnect_wifi,
    restart_all_nics,
    connect_to_ssid,
    enable_all_networks,
    disable_wifi,
    enable_wifi,
    network_dictionary,
    request_scan_all,
    scan_networks,
    tray_state,
    forget_network,
    ssid_is_saved,
    save_psk_network,
    update_psk_network,
    save_open_network,
    wpa_networks,
    wpa_reconfigure,
    wpa_save_config,
    wait_for_connection,
    EAP_METHODS,
    PHASE2_METHODS,
    get_system_ca_certificates,
    save_eap_network
)
from NetworkMgr.configuration import open_configuration, open_network_settings

from NetworkMgr.wg_api import (
    WIREGUARD_NOT_INSTALLED_MSG,
    wg_dictionary,
    wg_service_state,
    disable_wg,
    enable_wg,
    is_wireguard_installed,
    parse_wireguard_config
)
from NetworkMgr.openvpn_api import (
    OPENVPN_NOT_INSTALLED_MSG,
    openvpn_dictionary,
    openvpn_service_state,
    disable_openvpn,
    enable_openvpn,
    is_openvpn_installed,
    parse_openvpn_config
)
from NetworkMgr.ipsec_api import (
    disable_ipsec,
    enable_ipsec,
    ipsec_dictionary,
    is_ipsec_installed,
    parse_ipsec_config
)
from NetworkMgr.vpn_dialog import (
    import_vpn_file_dialog,
    show_connection_notification,
    show_ipsec_not_installed_alert,
    show_openvpn_not_installed_alert,
    show_wireguard_not_installed_alert,
    VPNConnectionDialog,
    OpenVPNAuthDialog
)

gettext.bindtextdomain('NetworkMgr', '/usr/local/share/locale')
gettext.textdomain('NetworkMgr')
_ = gettext.gettext

GObject.threads_init()

# Attempts on one network before its saved block is removed. One failure is
# not proof of a wrong password (issue #81); three is enough either way.
MAX_ATTEMPTS = 3

# Crisp inline SVG icons for the single-row connection items:
#   <Nome>   <botao1 (Connect / Red X Disconnect)><botao2 (Gear Configure)>
_STATUS_CONNECTED_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">
  <circle cx="5" cy="5" r="4" fill="#2ecc71"/>
</svg>"""

_STATUS_DISCONNECTED_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">
  <circle cx="5" cy="5" r="3.5" fill="none" stroke="#8b949e" stroke-width="1.5"/>
</svg>"""

_CONNECT_ICON_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <circle cx="8" cy="8" r="7" fill="#2ecc71" fill-opacity="0.18" stroke="#2ecc71" stroke-width="1.3"/>
  <path d="M6.4 4.8 L11.4 8 L6.4 11.2 Z" fill="#2ecc71"/>
</svg>"""

_DISCONNECT_RED_X_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <circle cx="8" cy="8" r="7" fill="#e74c3c" fill-opacity="0.22" stroke="#ff5252" stroke-width="1.3"/>
  <path d="M5.3 5.3 L10.7 10.7 M10.7 5.3 L5.3 10.7" stroke="#ff5252" stroke-width="2.0" stroke-linecap="round"/>
</svg>"""

_CONFIGURE_GEAR_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path fill="#c9d1d9" d="M6.9 1.5h2.2l.35 1.72c.42.14.81.37 1.15.65l1.67-.58 1.1 1.9-1.32 1.14c.06.22.1.44.1.67s-.04.45-.1.67l1.32 1.14-1.1 1.9-1.67-.58c-.34.28-.73.51-1.15.65L9.1 14.5H6.9l-.35-1.72a4.6 4.6 0 0 1-1.15-.65l-1.67.58-1.1-1.9 1.32-1.14A3.8 3.8 0 0 1 3.85 8c0-.23.04-.45.1-.67L2.63 6.19l1.1-1.9 1.67.58c.34-.28.73-.51 1.15-.65L6.9 1.5zm1.1 4.2A2.3 2.3 0 1 0 8 10.3 2.3 2.3 0 0 0 8 5.7z"/>
</svg>"""

_MENU_ROW_CSS_LOADED = False


def _ensure_menu_row_css():
    """Install compact icon-button styling for single-row menu items."""
    global _MENU_ROW_CSS_LOADED
    if _MENU_ROW_CSS_LOADED:
        return
    _MENU_ROW_CSS_LOADED = True
    try:
        screen = Gdk.Screen.get_default()
        if screen is None:
            return
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"""
            .nm-row-action-btn {
                min-width: 22px;
                min-height: 22px;
                padding: 2px 4px;
                margin: 0px;
                border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 0.14);
                background: rgba(255, 255, 255, 0.05);
            }
            .nm-row-action-btn:hover {
                background: rgba(255, 255, 255, 0.16);
                border-color: rgba(255, 255, 255, 0.28);
            }
            """
        )
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    except Exception:
        pass


def _svg_icon(svg_bytes, size=16):
    """Render an inline SVG byte string into a Gtk.Image of the given pixel size."""
    try:
        loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
        loader.set_size(size, size)
        loader.write(svg_bytes)
        loader.close()
        return Gtk.Image.new_from_pixbuf(loader.get_pixbuf())
    except Exception:
        return Gtk.Image.new_from_icon_name(
            "preferences-system-symbolic", Gtk.IconSize.MENU
        )



def _heading_label(text):
    """Build a dialog heading without going through the markup parser.

    Headings carry an SSID, so a name holding `&` or a tag would break the
    Pango parse or have its markup obeyed. Attributes leave the text alone.

    Args:
        text (str): the heading, already translated.

    Returns:
        Gtk.Label: the label, bold and one size up, showing text verbatim.
    """
    label = Gtk.Label(label=text)
    attributes = Pango.AttrList()
    attributes.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
    # PANGO_SCALE_LARGE is a C macro and not introspectable.
    attributes.insert(Pango.attr_scale_new(1.2))
    label.set_attributes(attributes)
    return label


class TrayIcon:
    """The status icon, its menu, and the thread that keeps them current."""

    def stop_manager(self, _widget):
        """Quit the application.

        Args:
            _widget (Gtk.Widget): the menu item that fired this, unused.
        """
        Gtk.main_quit()

    def __init__(self):
        self.cardinfo = None
        self.status_icon = Gtk.StatusIcon()
        self.status_icon.set_visible(True)
        self.status_icon.connect("activate", self.left_click)
        self.status_icon.connect('popup-menu', self.menu_requested)
        # Built on demand by the menu and dialog builders below.
        self.thr = None
        self.menu = None
        # Set while an attempt runs so the refresh does not draw over the
        # animation. Written from the worker; bool assignment is atomic.
        self.connecting = False
        self.connect_frame = 0
        # Failed attempts since the user last picked this network from the
        # menu. At three the saved block is removed, see MAX_ATTEMPTS.
        self.connect_attempts = 0
        self.traystate = tray_state()
        # Read once: 13 ms of shell, and it only changes on an rc.conf edit.
        self.wg_service = wg_service_state()
        self.openvpn_service = openvpn_service_state()
        self.window = None
        self.password = None
        self.eap_window = None
        self.eap_method_combo = None
        self.phase2_combo = None
        self.identity_entry = None
        self.anon_identity_entry = None
        self.eap_password = None
        self.ca_cert_chooser = None
        self.client_cert_chooser = None
        self.private_key_chooser = None
        self.private_key_passwd = None
        self.eap_rows = {}

    def left_click(self, status_icon):
        """Pop the menu up under a left click on the tray icon.

        Args:
            status_icon (Gtk.StatusIcon): the icon that was clicked.
        """
        button = 1
        time = Gtk.get_current_event_time()
        position = Gtk.StatusIcon.position_menu
        self.build_menu().popup(None, None, position, status_icon, button, time)

    def menu_requested(self, status_icon, button, time):
        """Pop the menu up for a right click or a popup-menu key press.

        Args:
            status_icon (Gtk.StatusIcon): the icon that was clicked.
            button (int): the mouse button number GTK reported.
            time (int): the event's timestamp, passed straight to popup().
        """
        position = Gtk.StatusIcon.position_menu
        self.build_menu().popup(None, None, position, status_icon, button, time)

    def _connection_menu_row(
        self, name, is_connected, on_toggle, on_configure=None, is_enabled=None
    ):
        """Build a compact single-row menu item: <Nome>   <botao1><botao2>.

        - <Nome>: Connection name with a subtle status indicator dot.
        - <botao1>: Connect icon when disabled/disconnected, or Red X icon when active.
        - <botao2>: Gear icon to open the connection's configuration window.
        """
        if is_enabled is None:
            is_enabled = is_connected
        _ensure_menu_row_css()
        menu_item = Gtk.MenuItem()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        status_dot = _svg_icon(
            _STATUS_CONNECTED_SVG if is_connected else _STATUS_DISCONNECTED_SVG,
            size=10,
        )
        row.pack_start(status_dot, False, False, 0)

        name_label = Gtk.Label(label=name)
        name_label.set_xalign(0.0)
        name_label.set_hexpand(True)
        name_label.set_margin_end(16)
        if is_connected:
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_weight_new(Pango.Weight.SEMIBOLD))
            name_label.set_attributes(attrs)
        row.pack_start(name_label, True, True, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        btn1 = Gtk.Button()
        btn1.set_relief(Gtk.ReliefStyle.NONE)
        btn1.set_can_focus(False)
        btn1.get_style_context().add_class("nm-row-action-btn")
        btn1.set_image(
            _svg_icon(
                _DISCONNECT_RED_X_SVG if is_enabled else _CONNECT_ICON_SVG,
                size=16,
            )
        )
        btn1.set_always_show_image(True)
        btn1.set_tooltip_text(
            _("Disconnect %s") % name if is_enabled else _("Connect %s") % name
        )
        btn_box.pack_start(btn1, False, False, 0)

        btn2 = None
        if on_configure is not None:
            btn2 = Gtk.Button()
            btn2.set_relief(Gtk.ReliefStyle.NONE)
            btn2.set_can_focus(False)
            btn2.get_style_context().add_class("nm-row-action-btn")
            btn2.set_image(_svg_icon(_CONFIGURE_GEAR_SVG, size=16))
            btn2.set_always_show_image(True)
            btn2.set_tooltip_text(_("Configure %s") % name)
            btn_box.pack_start(btn2, False, False, 0)

        row.pack_end(btn_box, False, False, 0)
        menu_item.add(row)

        action_fired = {"done": False}

        def _invoke(callback):
            if action_fired["done"] or callback is None:
                return
            action_fired["done"] = True
            if self.menu is not None:
                self.menu.popdown()
            GLib.idle_add(lambda: (callback(), False)[1])

        btn1.connect("clicked", lambda _b: _invoke(on_toggle))
        if btn2 is not None:
            btn2.connect("clicked", lambda _b: _invoke(on_configure))

        def _on_button_release(_item, event):
            # Gtk.Menu holds a pointer grab while open, so button-release-event
            # is delivered to the Gtk.MenuItem in the menu window's coordinate
            # space. Only trigger actions when the click lands on <botao2> or <botao1>.
            if btn2 is not None:
                alloc2 = btn2.get_allocation()
                if alloc2.width > 0 and (alloc2.x - 2) <= event.x <= (alloc2.x + alloc2.width + 2):
                    _invoke(on_configure)
                    return True
            alloc1 = btn1.get_allocation()
            if alloc1.width > 0 and (alloc1.x - 2) <= event.x <= (alloc1.x + alloc1.width + 2):
                _invoke(on_toggle)
                return True
            return True

        menu_item.connect("button-release-event", _on_button_release)
        return menu_item

    def build_menu(self):
        """Build the whole tray menu.

        The refresh tick collects only what the icon and the tooltip show,
        so the interfaces are read here instead. That is about 10 ms, which
        a click can afford. The scan list under each wireless card costs
        more again, so it is filled when its submenu opens rather than now.

        Returns:
            Gtk.Menu: the assembled menu, ready to pop up.
        """
        self.menu = Gtk.Menu()
        # Asked for, not waited on: this refreshes the list for the next
        # look, while the submenu below is drawn from what is known now.
        request_scan_all()
        # The refresh tick deliberately does not collect this.
        self.cardinfo = network_dictionary()
        wg_info = wg_dictionary(self.wg_service)
        if len(wg_info['configs']) > 0 and wg_info['service'] == 'NO':
            wg_title = Gtk.MenuItem()
            wg_title.set_label(_("WireGuard VPN"))
            wg_title.set_sensitive(False)
            self.menu.append(wg_title)
            self.menu.append(Gtk.SeparatorMenuItem())
            wg_devices = wg_info['configs']
            for wg_dev in wg_devices:
                connection_state = wg_devices[wg_dev]['state']
                connection_info = wg_devices[wg_dev]['info']
                wg_path = wg_devices[wg_dev].get('path', '')
                is_connected = connection_state == "Connected"
                toggle_cb = (
                    (lambda dev=wg_dev: self.disconnect_wg(None, dev))
                    if is_connected
                    else (lambda dev=wg_dev: self.connect_wg(None, dev))
                )
                config_cb = (
                    (lambda path=wg_path: self.configure_wg_profile(None, path))
                    if wg_path
                    else None
                )
                self.menu.append(
                    self._connection_menu_row(
                        connection_info, is_connected, toggle_cb, config_cb
                    )
                )
            self.menu.append(Gtk.SeparatorMenuItem())

        ovpn_info = openvpn_dictionary(self.openvpn_service)
        if len(ovpn_info['configs']) > 0:
            ovpn_title = Gtk.MenuItem()
            ovpn_title.set_label(_("OpenVPN"))
            ovpn_title.set_sensitive(False)
            self.menu.append(ovpn_title)
            self.menu.append(Gtk.SeparatorMenuItem())
            ovpn_devices = ovpn_info['configs']
            for ovpn_dev, ovpn_meta in ovpn_devices.items():
                connection_state = ovpn_meta['state']
                connection_info = ovpn_meta['info']
                ovpn_path = ovpn_meta.get('path', '')
                is_connected = connection_state == "Connected"
                toggle_cb = (
                    (
                        lambda dev=ovpn_dev, info=connection_info: self.disconnect_openvpn(
                            None, dev, info
                        )
                    )
                    if is_connected
                    else (
                        lambda dev=ovpn_dev, meta=ovpn_meta: self.connect_openvpn(
                            None, dev, meta
                        )
                    )
                )
                config_cb = (
                    (lambda path=ovpn_path: self.configure_openvpn_profile(None, path))
                    if ovpn_path
                    else None
                )
                self.menu.append(
                    self._connection_menu_row(
                        connection_info, is_connected, toggle_cb, config_cb
                    )
                )
            self.menu.append(Gtk.SeparatorMenuItem())

        ipsec_info = ipsec_dictionary()
        if len(ipsec_info['configs']) > 0:
            ipsec_title = Gtk.MenuItem()
            ipsec_title.set_label(_("IPsec / L2TP VPN"))
            ipsec_title.set_sensitive(False)
            self.menu.append(ipsec_title)
            self.menu.append(Gtk.SeparatorMenuItem())
            for ipsec_dev, ipsec_meta in ipsec_info['configs'].items():
                connection_state = ipsec_meta['state']
                connection_info = ipsec_meta['info']
                ipsec_path = ipsec_meta.get('path', '')
                is_connected = connection_state == "Connected"
                toggle_cb = (
                    (
                        lambda dev=ipsec_dev, info=connection_info: self.disconnect_ipsec(
                            None, dev, info
                        )
                    )
                    if is_connected
                    else (
                        lambda dev=ipsec_dev, meta=ipsec_meta: self.connect_ipsec(
                            None, dev, meta
                        )
                    )
                )
                config_cb = (
                    (lambda path=ipsec_path: self.configure_ipsec_profile(None, path))
                    if ipsec_path
                    else None
                )
                self.menu.append(
                    self._connection_menu_row(
                        connection_info, is_connected, toggle_cb, config_cb
                    )
                )
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
                wired_label = _("Wired %s (%s)") % (cardnum, netcard)
                if connection_state in ("Connected", "Disabled", "Disconnected"):
                    is_connected = connection_state == "Connected"
                    is_enabled = connection_state in ("Connected", "Disconnected")
                    toggle_cb = (
                        (lambda nc=netcard: self.disable_card(None, nc))
                        if is_enabled
                        else (lambda nc=netcard: self.enable_card(None, nc))
                    )
                    config_cb = (
                        lambda nc=netcard: self.configuration_window_open(None, nc)
                    )
                    self.menu.append(
                        self._connection_menu_row(
                            wired_label,
                            is_connected,
                            toggle_cb,
                            config_cb,
                            is_enabled=is_enabled,
                        )
                    )
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
                    enawifi.connect("activate", self.enable_wifi, netcard)
                    self.menu.append(enawifi)
                elif connection_state == "Disconnected":
                    d_title = Gtk.MenuItem()
                    d_title.set_label(_("WiFi %s Disconnected") % wifinum)
                    d_title.set_sensitive(False)
                    self.menu.append(d_title)
                    self.wifi_list_menu(netcard, None, False)
                    self.forget_list_menu(netcard)
                    diswifi = Gtk.MenuItem(_("Disable Wifi %s") % wifinum)
                    diswifi.connect("activate", self.disable_wifi, netcard)
                    self.menu.append(diswifi)
                else:
                    ssid = cards[netcard]['state']["ssid"]
                    signal = cards[netcard]['signal'] or 0
                    wc_title = Gtk.MenuItem(_("WiFi %s Connected") % wifinum)
                    wc_title.set_sensitive(False)
                    self.menu.append(wc_title)
                    connection_item = Gtk.ImageMenuItem(ssid)
                    connection_item.set_image(self.wifi_signal_icon(signal))
                    connection_item.show()
                    disconnect_item = Gtk.MenuItem(_("Disconnect from %s") % ssid)
                    disconnect_item.connect("activate", self.disconnect_wifi,
                                            netcard)
                    self.menu.append(connection_item)
                    self.menu.append(disconnect_item)
                    self.wifi_list_menu(netcard, ssid, True)
                    self.forget_list_menu(netcard)
                    diswifi = Gtk.MenuItem(_("Disable Wifi %s") % wifinum)
                    diswifi.connect("activate", self.disable_wifi, netcard)
                    self.menu.append(diswifi)
                    configure_item = Gtk.ImageMenuItem(_("Configure %s") % netcard)
                    configure_item.connect("activate", self.configuration_window_open, netcard)
                    self.menu.append(configure_item)
                self.menu.append(Gtk.SeparatorMenuItem())
                wifinum += 1

        settings_item = Gtk.MenuItem(_("Settings"))
        settings_item.connect("activate", self.open_settings_window)
        self.menu.append(settings_item)

        import_vpn_item = Gtk.MenuItem(_("Import VPN Configuration..."))
        import_vpn_item.connect("activate", self.import_vpn_configuration)
        self.menu.append(import_vpn_item)
        self.menu.append(Gtk.SeparatorMenuItem())
        open_item = Gtk.MenuItem(_("Restart Networking"))
        open_item.connect("activate", restart_all_nics)
        self.menu.append(open_item)
        close_manager = Gtk.MenuItem(_("Close Network Manager"))
        close_manager.connect("activate", self.stop_manager)
        self.menu.append(close_manager)
        self.menu.show_all()
        return self.menu

    def ssid_menu_item(self, network, wifi_card):
        """
        Build one clickable access point entry for the menu.

        Args:
            network (dict): the network's scan record from scan_networks.
            wifi_card (str): the interface the entry would connect.

        Returns:
            Gtk.ImageMenuItem: labelled with the SSID, carrying a signal icon
                that shows a padlock for anything but an open network, and
                wired to the dialog its security type calls for. A WPA3-only
                network is shown greyed out: driver_bsd offers no SAE.
        """
        ssid = network['ssid']
        if network['security'] == 'WPA3-SAE':
            menu_item = Gtk.ImageMenuItem(_("%s (WPA3 only)") % ssid)
            menu_item.set_image(self.wifi_signal_icon(network['signal'], True))
            menu_item.set_sensitive(False)
            menu_item.show()
            return menu_item
        menu_item = Gtk.ImageMenuItem(ssid)
        if network['security'] == 'OPEN':
            is_secure = False
            click_action = self.connect_open_network
            click_argument = ssid
        elif network['enterprise']:
            is_secure = True
            click_action = self.connect_enterprise_network
            click_argument = network
        else:
            is_secure = True
            click_action = self.connect_psk_network
            click_argument = network
        menu_item.set_image(self.wifi_signal_icon(network['signal'], is_secure))
        menu_item.connect("activate", click_action, click_argument, wifi_card)
        menu_item.show()
        return menu_item

    def wifi_list_menu(self, wifi_card, cssid, passes):
        """
        Add the "Available Connections" submenu for one wireless card.

        The submenu fills itself when opened, so a tray click does not pay
        for a scan read.

        Args:
            wifi_card (str): the interface whose scan results to list.
            cssid (str or None): the SSID already connected, if any.
            passes (bool): True to leave cssid out of the list, so the card
                the user is already on is not offered again.
        """
        wiconncmenu = Gtk.Menu()
        avconnmenu = Gtk.MenuItem(_("Available Connections"))
        avconnmenu.set_submenu(wiconncmenu)
        wiconncmenu.connect("show", self.fill_wifi_list, wifi_card, cssid,
                            passes)
        self.menu.append(avconnmenu)

    def forget_list_menu(self, wifi_card):
        """
        Add the "Forget Network" submenu for one wireless card.

        The only way to correct a network saved with the wrong passphrase:
        clicking it connects with the stored key, and an access point that
        never answers never refuses, so nothing reopens the dialog.

        Args:
            wifi_card (str): the interface whose saved networks to list.
        """
        forget_menu = Gtk.Menu()
        forget_item = Gtk.MenuItem(_("Forget Network"))
        forget_item.set_submenu(forget_menu)
        forget_menu.connect("show", self.fill_forget_list, wifi_card)
        self.menu.append(forget_item)

    def fill_forget_list(self, submenu, wifi_card):
        """
        List the saved networks, filled when the submenu is opened.

        These come from the daemon rather than a scan, so a network that is
        saved but out of range can still be forgotten.

        Args:
            submenu (Gtk.Menu): the submenu to fill.
            wifi_card (str): the interface whose saved networks to list.
        """
        for child in submenu.get_children():
            submenu.remove(child)
        for network in wpa_networks(wifi_card):
            entry = Gtk.MenuItem(network['ssid'])
            entry.connect("activate", self.forget_ssid, network['ssid'],
                          wifi_card)
            entry.show()
            submenu.append(entry)

    def forget_ssid(self, _widget, ssid, wifi_card):
        """
        Remove one saved network.

        Args:
            _widget (Gtk.Widget): the menu item, unused.
            ssid (str): the network to forget.
            wifi_card (str): the interface it is saved on.
        """
        wpa_reconfigure(wifi_card)
        forget_network(ssid, wifi_card)
        self.update_info()

    def fill_wifi_list(self, submenu, wifi_card, cssid, passes):
        """
        Read the scan table and fill the Available Connections submenu.

        Args:
            submenu (Gtk.Menu): the submenu to fill.
            wifi_card (str): the interface whose scan results to list.
            cssid (str or None): the SSID already connected, if any.
            passes (bool): True to leave cssid out of the list.
        """
        for child in submenu.get_children():
            submenu.remove(child)
        for ssid, network in scan_networks(wifi_card).items():
            if passes and cssid == ssid:
                continue
            submenu.append(self.ssid_menu_item(network, wifi_card))

    def configuration_window_open(self, _widget, interface):
        """Open the configuration window for one interface.

        Args:
            _widget (Gtk.Widget): the menu item, unused.
            interface (str): interface name to configure.
        """
        open_configuration(interface)

    def open_settings_window(self, _widget):
        """Open the unified NetworkManager-style Settings window."""
        open_network_settings(on_changed=self.update_info)

    def connect_open_network(self, _widget, ssid, wifi_card):
        """
        Join an open network, asking for nothing.

        Args:
            _widget (Gtk.Widget): the menu item, unused.
            ssid (str): the network name that was clicked.
            wifi_card (str): the interface to connect.
        """
        self.connect_attempts = 0
        wpa_reconfigure(wifi_card)
        if not ssid_is_saved(ssid, wifi_card) \
                and save_open_network(ssid, wifi_card) is None:
            self.connection_failed(ssid, wifi_card)
            return
        self.start_connection(ssid, None, wifi_card)

    def connect_psk_network(self, _widget, network, wifi_card):
        """
        Join a passphrase network, asking for the password if it is new.

        Args:
            _widget (Gtk.Widget): the menu item, unused.
            network (dict): the clicked network's scan record.
            wifi_card (str): the interface to connect.
        """
        self.connect_attempts = 0
        if ssid_is_saved(network['ssid'], wifi_card):
            wpa_reconfigure(wifi_card)
            self.start_connection(network['ssid'], network, wifi_card)
        else:
            self.passphrase_dialog(network, wifi_card, False)

    def connect_enterprise_network(self, _widget, network, wifi_card):
        """
        Join an enterprise network, asking for credentials if it is new.

        Args:
            _widget (Gtk.Widget): the menu item, unused.
            network (dict): the clicked network's scan record.
            wifi_card (str): the interface to connect.
        """
        self.connect_attempts = 0
        if ssid_is_saved(network['ssid'], wifi_card):
            wpa_reconfigure(wifi_card)
            self.start_connection(network['ssid'], network, wifi_card,
                                  enterprise=True)
        else:
            self.eap_dialog(network, wifi_card, False)

    def disconnect_wifi(self, _widget, wifi_card):
        """Drop the current wireless association.

        Args:
            _widget (Gtk.Widget): the menu item, unused.
            wifi_card (str): wireless interface name.
        """
        ssid = wifi_card
        if self.cardinfo and wifi_card in self.cardinfo.get('cards', {}):
            ssid = (
                self.cardinfo['cards'][wifi_card]['state'].get('ssid')
                or wifi_card
            )
        disconnect_wifi(wifi_card)
        self.update_info()
        show_connection_notification(ssid, False)

    def disable_wifi(self, _widget, wifi_card):
        """Take a wireless interface down.

        Args:
            _widget (Gtk.Widget): the menu item, unused.
            wifi_card (str): wireless interface name.
        """
        disable_wifi(wifi_card)
        self.update_info()
        show_connection_notification(wifi_card, False)

    def enable_wifi(self, _widget, wifi_card):
        """Bring a wireless interface back up.

        Args:
            _widget (Gtk.Widget): the menu item, unused.
            wifi_card (str): wireless interface name.
        """
        enable_wifi(wifi_card)
        self.update_info()
        show_connection_notification(wifi_card, True)

    def enable_card(self, _widget, netcard):
        """Start a wired interface.

        Args:
            _widget (Gtk.Widget): the menu item, unused.
            netcard (str): interface name.
        """
        start_network_card(netcard)
        self.update_info()
        show_connection_notification(netcard, True)

    def disable_card(self, _widget, netcard):
        """Stop a wired interface.

        Args:
            _widget (Gtk.Widget): the menu item, unused.
            netcard (str): interface name.
        """
        stop_network_card(netcard)
        self.update_info()
        show_connection_notification(netcard, False)

    def connect_wg(self, _widget, wg_device):
        """Bring a WireGuard tunnel up.

        Args:
            _widget (Gtk.Widget): the menu item, unused.
            wg_device (str): the tunnel's configuration name, without .conf.
        """
        if not is_wireguard_installed():
            show_wireguard_not_installed_alert()
            return
        ok, err_msg = enable_wg(wg_device)
        self.update_info()
        if not ok:
            if err_msg == WIREGUARD_NOT_INSTALLED_MSG:
                show_wireguard_not_installed_alert()
                return
            dialog = Gtk.MessageDialog(
                None, 0, Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE,
                _("Could not connect to %s") % wg_device
            )
            dialog.format_secondary_text(err_msg)
            dialog.run()
            dialog.destroy()
            return
        show_connection_notification(wg_device, True)

    def disconnect_wg(self, _widget, wg_device):
        """Take a WireGuard tunnel down.

        Args:
            _widget (Gtk.Widget): the menu item, unused.
            wg_device (str): the tunnel's configuration name, without .conf.
        """
        disable_wg(wg_device)
        self.update_info()
        show_connection_notification(wg_device, False)

    def connect_openvpn(self, _widget, ovpn_dev, ovpn_meta):
        """Bring an OpenVPN tunnel up, prompting for credentials if required."""
        if not is_openvpn_installed():
            show_openvpn_not_installed_alert()
            return
        display_name = ovpn_meta.get('info', ovpn_dev)
        if ovpn_meta.get('needs_auth'):
            dialog = OpenVPNAuthDialog(
                ovpn_dev,
                display_name,
                initial_user=ovpn_meta.get('username', ''),
                on_submit=lambda dev, u, p, dn=display_name: self._do_connect_openvpn(
                    dev, u, p, dn
                ),
            )
            dialog.show_all()
            return
        self._do_connect_openvpn(ovpn_dev, None, None, display_name)

    def _do_connect_openvpn(self, ovpn_dev, username, password, display_name=None):
        """Start OpenVPN and report any startup failure."""
        if not is_openvpn_installed():
            show_openvpn_not_installed_alert()
            return
        label_name = display_name or ovpn_dev
        ok, err_msg = enable_openvpn(ovpn_dev, username=username, password=password)
        self.update_info()
        if not ok:
            if err_msg == OPENVPN_NOT_INSTALLED_MSG:
                show_openvpn_not_installed_alert()
                return
            dialog = Gtk.MessageDialog(
                None, 0, Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE,
                _("Could not connect to %s") % label_name
            )
            dialog.format_secondary_text(err_msg)
            dialog.run()
            dialog.destroy()
            return
        show_connection_notification(label_name, True)

    def disconnect_openvpn(self, _widget, ovpn_dev, display_name=None):
        """Take an OpenVPN tunnel down."""
        disable_openvpn(ovpn_dev)
        self.update_info()
        show_connection_notification(display_name or ovpn_dev, False)

    def import_vpn_configuration(self, _widget):
        """Open the VPN file importer dialog from the tray menu."""
        import_vpn_file_dialog(
            parent=None,
            on_saved=lambda _pid, _vtype: self.update_info(),
        )

    def configure_wg_profile(self, _widget, wg_path):
        """Open the VPN editor for an existing WireGuard configuration."""
        try:
            cfg = parse_wireguard_config(wg_path)
        except ValueError:
            return
        editor = VPNConnectionDialog(
            cfg,
            parent=None,
            on_saved=lambda _pid, _vtype: self.update_info(),
        )
        editor.show_all()
        editor.refresh_dynamic_visibility()

    def configure_openvpn_profile(self, _widget, ovpn_path):
        """Open the VPN editor for an existing OpenVPN configuration."""
        try:
            cfg = parse_openvpn_config(ovpn_path)
        except ValueError:
            return
        editor = VPNConnectionDialog(
            cfg,
            parent=None,
            on_saved=lambda _pid, _vtype: self.update_info(),
        )
        editor.show_all()
        editor.refresh_dynamic_visibility()

    def connect_ipsec(self, _widget, ipsec_dev, ipsec_meta):
        """Bring an IPsec (IKEv2/IKEv1) or L2TP/IPsec tunnel up."""
        protocol = ipsec_meta.get('protocol', 'l2tp-ipsec')
        display_name = ipsec_meta.get('info', ipsec_dev)
        if not is_ipsec_installed(protocol):
            show_ipsec_not_installed_alert(protocol)
            return
        ok, err_msg = enable_ipsec(ipsec_dev)
        self.update_info()
        if not ok:
            dialog = Gtk.MessageDialog(
                None, 0, Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE,
                _("Could not connect to %s") % display_name
            )
            dialog.format_secondary_text(err_msg)
            dialog.run()
            dialog.destroy()
            return
        show_connection_notification(display_name, True)

    def disconnect_ipsec(self, _widget, ipsec_dev, display_name=None):
        """Take an IPsec or L2TP/IPsec tunnel down."""
        disable_ipsec(ipsec_dev)
        self.update_info()
        show_connection_notification(display_name or ipsec_dev, False)

    def configure_ipsec_profile(self, _widget, ipsec_path):
        """Open the VPN editor for an existing IPsec or L2TP/IPsec configuration."""
        try:
            cfg = parse_ipsec_config(ipsec_path)
        except ValueError:
            return
        editor = VPNConnectionDialog(
            cfg,
            parent=None,
            on_saved=lambda _pid, _vtype: self.update_info(),
        )
        editor.show_all()
        editor.refresh_dynamic_visibility()

    def signal_icon_name(self, signal, suffix):
        """Pick the signal icon name for a strength percentage.

        Args:
            signal (int): signal strength as a percentage.
            suffix (str): icon name suffix, "-secure" or empty.

        Returns:
            str: an icon name from the nm-signal set.
        """
        if signal > 75:
            icon_name = f"nm-signal-100{suffix}"
        elif signal > 50:
            icon_name = f"nm-signal-75{suffix}"
        elif signal > 25:
            icon_name = f"nm-signal-50{suffix}"
        elif signal > 5:
            icon_name = f"nm-signal-25{suffix}"
        else:
            icon_name = f"nm-signal-00{suffix}"
        return icon_name

    def wifi_signal_icon(self, signal, is_secure=False):
        """Build the signal strength image shown next to an SSID.

        Args:
            signal (int): signal strength as a percentage.
            is_secure (bool): True to use the padlocked variant.

        Returns:
            Gtk.Image: a realised image widget.
        """
        img = Gtk.Image()
        suffix = ""
        if is_secure:
            suffix = "-secure"
        icon_name = self.signal_icon_name(signal, suffix)
        img.set_from_icon_name(icon_name, Gtk.IconSize.MENU)
        img.show()
        return img

    def update_info(self):
        """
        Refresh the icon and the tooltip.

        The refresh-tick path: only the default-route interface, whether it
        is up, and its signal. The menu's data is collected on menu open.

        No lock. tray_state() builds the whole dict before it is assigned,
        so a reader sees the old one or the new one, never a half-built one.
        """
        self.traystate = tray_state()
        GLib.idle_add(self.update_tray)

    def update_tray(self):
        """Redraw the tray icon and its tooltip from the last light refresh.

        Returns:
            bool: False, so GLib.idle_add does not call this again.
        """
        self.update_tray_icon()
        self.status_icon.set_tooltip_text(self.traystate['tooltip'])
        return False

    def update_tray_loop(self):
        """Refresh the tray for the life of the app.

        Thirty seconds, two to four commands, about 5 ms. It catches only
        passive change: a cable pulled, a link dropping, signal drifting.
        Anything the user does refreshes at the end of the action.

        The scan request goes out here too, so the BSS table is warm before
        anyone opens the menu. It is asked for, never waited on.
        """
        while True:
            self.update_info()
            request_scan_all()
            sleep(30)

    def start_icon_animation(self):
        """Begin cycling the signal icons for a connection attempt.

        Returns:
            bool: False, so GLib.idle_add does not repeat this.
        """
        if self.connecting:
            return False
        self.connecting = True
        self.connect_frame = 0
        # 300 ms a frame: slow enough to read as deliberate, fast enough to
        # look busy.
        GLib.timeout_add(300, self.next_animation_frame)
        return False

    def next_animation_frame(self):
        """Draw the next frame of the connecting animation.

        Returns:
            bool: True to stay on the timer, False once the attempt has
                finished, which removes the timeout.
        """
        if not self.connecting:
            return False
        # Filling bars: the signal icons already shipped, cycled the way
        # NetworkManager does it, so there is no new artwork to install.
        frames = ('nm-signal-00', 'nm-signal-25', 'nm-signal-50',
                  'nm-signal-75', 'nm-signal-100')
        self.status_icon.set_from_icon_name(
            frames[self.connect_frame % len(frames)]
        )
        self.connect_frame += 1
        return True

    def stop_icon_animation(self):
        """End the animation and put the real icon back.

        Returns:
            bool: False, so GLib.idle_add does not repeat this.
        """
        self.connecting = False
        self.update_tray()
        return False

    def update_tray_icon(self):
        """Set the tray icon to match the last light refresh.

        Does nothing while a connection attempt is running, so the refresh
        loop cannot overwrite the animation mid-attempt.
        """
        if self.connecting:
            return
        kind = self.traystate['kind']
        if kind is None:
            icon_name = 'nm-no-connection'
        elif kind == 'wire':
            icon_name = 'nm-device-wired'
        else:
            wifi_state = (self.traystate['signal']
                          if self.traystate['connection'] == 'Connected'
                          else None)
            if wifi_state is None:
                icon_name = 'nm-no-connection'
            else:
                icon_name = self.signal_icon_name(wifi_state, '')
        self.status_icon.set_from_icon_name(icon_name)

    def run(self):
        """Start the background refresh thread and hand control to GTK.

        This is the only place the refresh thread is created. It starts
        before Gtk.main(), so it is already running by the time any click
        can arrive, which is why the click handlers do not check on it.
        """
        self.thr = threading.Thread(target=self.update_tray_loop)
        self.thr.daemon = True
        self.thr.start()
        Gtk.main()

    def close(self, _widget):
        """Hide the passphrase dialog.

        Args:
            _widget (Gtk.Widget): the Cancel button, unused.
        """
        self.window.hide()

    def add_to_wpa_supplicant(self, _widget, network, card):
        """
        Save the typed passphrase and start connecting in the background.

        Args:
            _widget (Gtk.Widget): the Connect button, unused.
            network (dict): the network's scan record.
            card (str): the interface to connect.
        """
        pwd = self.password.get_text()
        ssid = network['ssid']
        self.window.hide()
        wpa_reconfigure(card)
        # Change the one field, do not delete and rebuild the block.
        if ssid_is_saved(ssid, card):
            stored = update_psk_network(ssid, pwd, card)
        else:
            stored = save_psk_network(ssid, network['security'], pwd,
                                      card) is not None
        if not stored:
            self.connection_failed(ssid, card)
            return
        self.start_connection(ssid, network, card)

    def start_connection(self, ssid, network, card, enterprise=False):
        """
        Begin joining a network on a worker thread.

        The attempt takes up to thirty seconds, so it must not run on the
        GTK thread.

        Args:
            ssid (str): the network name to join.
            network (dict or None): the network's scan record, needed to
                rebuild the credentials dialog if the key is refused. None
                for an open network, which has no dialog.
            card (str): the interface to connect.
            enterprise (bool): True to reopen the EAP dialog rather than the
                passphrase one when credentials are refused.
        """
        _thread.start_new_thread(
            self.try_to_connect_to_ssid,
            (ssid, network, card, enterprise)
        )

    def try_to_connect_to_ssid(self, ssid, network, card, enterprise=False):
        """
        Connect, then report the outcome.

        Runs on its own thread, so it must reach the UI through
        GLib.idle_add.

        Args:
            ssid (str): the network name.
            network (dict or None): the network's scan record, or None for
                an open network.
            card (str): the interface to connect.
            enterprise (bool): True to reopen the EAP dialog on refusal.
        """
        GLib.idle_add(self.start_icon_animation)
        try:
            if not connect_to_ssid(ssid, card):
                GLib.idle_add(self.connection_failed, ssid, card)
                return
            if wait_for_connection(card, ssid):
                # It works, so now it is worth keeping. Until this point the
                # network existed only in the daemon.
                wpa_save_config(card)
                GLib.idle_add(show_connection_notification, ssid, True)
            else:
                self.connect_attempts += 1
                if network is not None and self.connect_attempts < MAX_ATTEMPTS:
                    GLib.idle_add(self.reopen_credentials_dialog, network, card,
                                  enterprise)
                else:
                    # Out of tries, or an open network with nothing to
                    # retype. Either way the block does not work, so it goes.
                    forget_network(ssid, card)
                    GLib.idle_add(self.connection_failed, ssid, card, True)
        finally:
            # select_network disabled the others; leaving them disabled
            # would strand the card.
            enable_all_networks(card)
            # Refresh before the animation ends: stop_icon_animation draws
            # whatever traystate holds.
            self.update_info()
            GLib.idle_add(self.stop_icon_animation)

    def reopen_credentials_dialog(self, network, card, enterprise=False):
        """
        Reopen the credentials dialog after an attempt did not connect.

        Args:
            network (dict): the network's scan record.
            card (str): the interface to connect.
            enterprise (bool): True for the EAP dialog, False for the
                passphrase one.
        """
        if enterprise:
            self.eap_dialog(network, card, True)
        else:
            self.passphrase_dialog(network, card, True)

    def connection_failed(self, ssid, card, timed_out=False):
        """
        Tell the user the card never joined, without blaming the password.

        Args:
            ssid (str): the network that was not joined.
            card (str): the interface that tried.
            timed_out (bool): True when an attempt ran and the card never
                joined. False when no attempt was made because the daemon
                did not answer or refused the network.

        Returns:
            bool: False, so GLib.idle_add does not call this again.
        """
        if timed_out:
            detail = _(
                "%(card)s did not associate with %(ssid)s before timing out."
                "\n\nA weak signal is the usual cause."
            ) % {'card': card, 'ssid': ssid}
        else:
            detail = _("wpa_supplicant did not accept the request on %s.") % card
        dialog = Gtk.MessageDialog(
            None, 0, Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE,
            _("Could not connect to %s") % ssid
        )
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()
        return False

    def toggle_password_visibility(self, widget):
        """
        Show or hide the typed password.

        Args:
            widget (Gtk.CheckButton): the "Show password" box.
        """
        self.password.set_visibility(widget.get_active())

    def passphrase_dialog(self, network, card, failed):
        """
        Build and show the passphrase dialog for one network.

        Args:
            network (dict): the network's scan record.
            card (str): the interface the password is for.
            failed (bool): True when a previous attempt did not connect,
                which only changes the heading.

        Returns:
            str: 'Done', kept because the caller has always ignored it.
        """
        ssid = network['ssid']
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
        if failed:
            # A refused key and a card that never answered look identical
            # on this driver, so the wording blames neither.
            title = _("Could not connect to %s. Try again.") % ssid
        else:
            title = _("Authentication required by %s Wi-Fi Network") % ssid
        label = _heading_label(title)
        pwd_label = Gtk.Label(_("Password:"))
        self.password = Gtk.Entry()
        self.password.set_visibility(False)
        check = Gtk.CheckButton(_("Show password"))
        check.connect("toggled", self.toggle_password_visibility)
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
        connect.connect("clicked", self.add_to_wpa_supplicant, network, card)
        table = Gtk.Table(1, 2, True)
        table.set_col_spacings(10)
        table.attach(connect, 4, 5, 0, 1)
        table.attach(cancel, 3, 4, 0, 1)
        box2.pack_end(table, True, True, 5)
        self.window.show_all()
        return 'Done'

    def add_enterprise_to_wpa_supplicant(self, _widget, network, card):
        """
        Collect the EAP form, save it, and start connecting in the background.

        Args:
            _widget (Gtk.Widget): the Connect button, unused.
            network (dict): the network's scan record.
            card (str): the interface to connect.
        """
        eap_config = {
            'eap_method': self.eap_method_combo.get_active_text(),
            'identity': self.identity_entry.get_text(),
            'password': self.eap_password.get_text(),
            'phase2': self.phase2_combo.get_active_text() if self.phase2_combo is not None else 'MSCHAPV2',
            'anonymous_identity': self.anon_identity_entry.get_text() if self.anon_identity_entry is not None else '',
        }

        # Get CA certificate path
        if self.ca_cert_chooser is not None:
            ca_file = self.ca_cert_chooser.get_filename()
            if ca_file:
                eap_config['ca_cert'] = ca_file

        # For TLS, get client certificate and key
        if eap_config['eap_method'] == 'TLS':
            if self.client_cert_chooser is not None:
                client_cert = self.client_cert_chooser.get_filename()
                if client_cert:
                    eap_config['client_cert'] = client_cert
            if self.private_key_chooser is not None:
                private_key = self.private_key_chooser.get_filename()
                if private_key:
                    eap_config['private_key'] = private_key
            if self.private_key_passwd is not None:
                eap_config['private_key_passwd'] = self.private_key_passwd.get_text()

        self.eap_window.hide()
        wpa_reconfigure(card)
        if save_eap_network(network['ssid'], eap_config, card) is None:
            self.connection_failed(network['ssid'], card)
            return
        self.start_connection(network['ssid'], network, card, enterprise=True)

    def on_eap_method_changed(self, combo):
        """Show only the fields the chosen EAP method uses.

        Each row is a label and a field, hidden as a pair. Hiding the field
        alone leaves its label naming an empty cell.

        Args:
            combo (Gtk.ComboBoxText): the EAP method chooser.
        """
        method = combo.get_active_text()
        tls = method == 'TLS'
        shown = {
            'phase2': method in ('PEAP', 'TTLS'),
            'password': not tls,
            'client_cert': tls,
            'private_key': tls,
            'private_key_passwd': tls,
        }
        for name, visible in shown.items():
            for widget in self.eap_rows.get(name, ()):
                widget.set_visible(visible)

    def close_eap_window(self, _widget):
        """Hide the enterprise credentials dialog.

        Args:
            _widget (Gtk.Widget): the Cancel button, unused.
        """
        self.eap_window.hide()

    def on_eap_password_check(self, widget):
        """Show or hide the typed EAP password.

        Args:
            widget (Gtk.CheckButton): the "show password" box.
        """
        self.eap_password.set_visibility(widget.get_active())

    def eap_dialog(self, network, card, failed):
        """
        Build and show the EAP credentials dialog for one network.

        Args:
            network (dict): the network's scan record.
            card (str): the interface the credentials are for.
            failed (bool): True to title the window as a failed attempt.

        Returns:
            str: 'Done', kept because the caller has always ignored it.
        """
        ssid = network['ssid']
        self.eap_rows = {}
        self.eap_window = Gtk.Window()
        self.eap_window.set_title(_("Enterprise Wi-Fi Authentication"))
        self.eap_window.set_border_width(10)
        self.eap_window.set_size_request(550, 450)

        main_box = Gtk.VBox(spacing=10)
        self.eap_window.add(main_box)

        # Title
        if failed:
            title_text = _("%s Enterprise Authentication Failed") % ssid
        else:
            title_text = _("Enterprise Authentication for %s") % ssid
        title_label = _heading_label(title_text)
        main_box.pack_start(title_label, False, False, 5)

        security_label = Gtk.Label(_("Security: %s") % network['security'])
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
        phase2_box = Gtk.HBox(spacing=5)
        phase2_label = Gtk.Label(_("Inner Auth:"))
        phase2_label.set_halign(Gtk.Align.END)
        grid.attach(phase2_label, 0, row, 1, 1)
        self.phase2_combo = Gtk.ComboBoxText()
        for method in PHASE2_METHODS:
            self.phase2_combo.append_text(method)
        self.phase2_combo.set_active(0)  # Default to MSCHAPV2
        phase2_box.pack_start(self.phase2_combo, True, True, 0)
        grid.attach(phase2_box, 1, row, 2, 1)
        self.eap_rows['phase2'] = (phase2_label, phase2_box)
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
        password_box = Gtk.VBox()
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
        password_box.pack_start(pwd_hbox, True, True, 0)
        grid.attach(password_box, 1, row, 2, 1)
        self.eap_rows['password'] = (pwd_label, password_box)
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
        client_cert_box = Gtk.HBox(spacing=5)
        client_cert_label = Gtk.Label(_("Client Cert:"))
        client_cert_label.set_halign(Gtk.Align.END)
        grid.attach(client_cert_label, 0, row, 1, 1)
        self.client_cert_chooser = Gtk.FileChooserButton(
            title=_("Select Client Certificate"),
            action=Gtk.FileChooserAction.OPEN
        )
        self.client_cert_chooser.add_filter(ca_filter)
        client_cert_box.pack_start(self.client_cert_chooser, True, True, 0)
        grid.attach(client_cert_box, 1, row, 2, 1)
        self.eap_rows['client_cert'] = (client_cert_label, client_cert_box)
        row += 1

        # Private Key
        private_key_box = Gtk.HBox(spacing=5)
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
        private_key_box.pack_start(self.private_key_chooser, True, True, 0)
        grid.attach(private_key_box, 1, row, 2, 1)
        self.eap_rows['private_key'] = (key_label, private_key_box)
        row += 1

        # Private Key Password
        private_key_passwd_box = Gtk.HBox(spacing=5)
        key_pwd_label = Gtk.Label(_("Key Password:"))
        key_pwd_label.set_halign(Gtk.Align.END)
        grid.attach(key_pwd_label, 0, row, 1, 1)
        self.private_key_passwd = Gtk.Entry()
        self.private_key_passwd.set_visibility(False)
        private_key_passwd_box.pack_start(self.private_key_passwd, True, True, 0)
        grid.attach(private_key_passwd_box, 1, row, 2, 1)
        self.eap_rows['private_key_passwd'] = (key_pwd_label,
                                               private_key_passwd_box)
        row += 1

        # Buttons
        button_box = Gtk.HBox(spacing=10)
        button_box.set_halign(Gtk.Align.END)
        main_box.pack_start(button_box, False, False, 5)

        cancel_btn = Gtk.Button(stock=Gtk.STOCK_CANCEL)
        cancel_btn.connect("clicked", self.close_eap_window)
        button_box.pack_start(cancel_btn, False, False, 0)

        connect_btn = Gtk.Button(stock=Gtk.STOCK_CONNECT)
        connect_btn.connect("clicked", self.add_enterprise_to_wpa_supplicant, network, card)
        button_box.pack_start(connect_btn, False, False, 0)

        self.eap_window.show_all()
        # Trigger visibility update
        self.on_eap_method_changed(self.eap_method_combo)
        return 'Done'
