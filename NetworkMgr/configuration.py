#!/usr/bin/env python

"""The per-interface network configuration window.

Two tabs, IPv4 and IPv6, each offering an automatic mode (DHCP or SLAAC) or
a manual address, mask, gateway, DNS and search domain. Saving writes
rc.conf through sysrc and /etc/resolv.conf directly, then applies the same
settings to the running system through NetworkMgr.net_api. Every value is
checked by NetworkMgr.validate first, since rc.conf runs as shell code.
"""

import os
import re
from subprocess import DEVNULL, run

import gi
gi.require_version('Gtk', '3.0')

# gi.require_version() has to run before the typelib is loaded, so the
# imports below cannot be hoisted above it.
# pylint: disable=wrong-import-position
from gi.repository import Gtk, GLib, Pango
from NetworkMgr.net_api import (
    default_card,
    disable_wifi,
    enable_wifi,
    network_dictionary,
    nics_list,
    restart_card_network,
    restart_routing_and_dhcp,
    start_network_card,
    start_static_network,
    start_static_ipv6_network,
    stop_network_card,
    enable_slaac,
    disable_slaac,
    wait_for_address
)
from NetworkMgr.query import get_interface_settings, get_interface_settings_ipv6
from NetworkMgr import validate
from NetworkMgr.openvpn_api import (
    OPENVPN_NOT_INSTALLED_MSG,
    default_openvpn_config,
    delete_openvpn_config,
    disable_openvpn,
    enable_openvpn,
    is_openvpn_installed,
    openvpn_dictionary,
    parse_openvpn_config,
)
from NetworkMgr.wg_api import (
    WIREGUARD_NOT_INSTALLED_MSG,
    default_wireguard_config,
    delete_wireguard_config,
    disable_wg,
    enable_wg,
    is_wireguard_installed,
    parse_wireguard_config,
    wg_dictionary,
    wg_service_state,
)
from NetworkMgr.ipsec_api import (
    default_ipsec_config,
    delete_ipsec_config,
    disable_ipsec,
    enable_ipsec,
    ipsec_dictionary,
    is_ipsec_installed,
    parse_ipsec_config,
)
from NetworkMgr.vpn_dialog import (
    OpenVPNAuthDialog,
    VPNConnectionDialog,
    import_vpn_file_dialog,
    show_connection_notification,
    show_ipsec_not_installed_alert,
    show_openvpn_not_installed_alert,
    show_wireguard_not_installed_alert,
)

# What set_rc_conf lets into rc.conf: the characters an interface name,
# address, netmask or keyword such as "WPA DHCP" can hold. No quote, $,
# backtick, backslash or newline can get through.
RC_CONF_SAFE_REGEX = re.compile(r'[A-Za-z0-9_.:%/ -]*')
# An rc.conf variable name. Interface names go through
# validate.rc_conf_interface first, so em0.10 arrives as em0_10.
RC_CONF_NAME_REGEX = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')

INTERFACE_ROUTES_DIR = '/usr/local/etc/networkmgr/routes'


_PENDING_REMOVED_ROUTES = {}


def load_interface_routes(nic, target_dir=INTERFACE_ROUTES_DIR):
    """Load saved IPv4 and IPv6 static routes for `nic`.

    Returns:
        tuple[list[dict], list[dict]]: `(ipv4_routes, ipv6_routes)`.
    """
    ipv4_routes = []
    ipv6_routes = []
    if not nic:
        return ipv4_routes, ipv6_routes
    rc_nic = validate.rc_conf_interface(nic)
    path = os.path.join(target_dir, f'{rc_nic}.routes')
    if not os.path.isfile(path):
        return ipv4_routes, ipv6_routes
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                sline = line.strip()
                if not sline or sline.startswith('#') or '=' not in sline:
                    continue
                k, v = [p.strip() for p in sline.split('=', 1)]
                parts = [p.strip() for p in v.split(',')]
                if k == 'ipv4_route' and len(parts) >= 3:
                    ipv4_routes.append({
                        'network': parts[0],
                        'netmask': parts[1],
                        'gateway': parts[2],
                    })
                elif k == 'ipv6_route' and len(parts) >= 3:
                    ipv6_routes.append({
                        'network': parts[0],
                        'prefixlen': parts[1],
                        'gateway': parts[2],
                    })
    except OSError:
        pass
    return ipv4_routes, ipv6_routes


def _sync_rc_conf_routes(rc_nic, valid_r4, valid_r6):
    """Synchronize per-interface static routes with FreeBSD `/etc/rc.conf`."""
    try:
        # IPv4 static_routes
        res4 = run(
            ['sysrc', '-n', 'static_routes'],
            stdout=PIPE,
            stderr=DEVNULL,
            universal_newlines=True,
            check=False,
        )
        cur4 = (res4.stdout or '').strip().split() if res4.returncode == 0 else []
        prefix4 = f'nm_{rc_nic}_'
        kept4 = []
        for tok in cur4:
            if tok.startswith(prefix4):
                run(['sysrc', '-x', f'route_{tok}'], stdout=DEVNULL, stderr=DEVNULL, check=False)
            else:
                kept4.append(tok)
        for idx, (net_ok, mask_ok, gw_ok) in enumerate(valid_r4):
            rname = f'{prefix4}{idx}'
            run(
                ['sysrc', f'route_{rname}=-net {net_ok} {gw_ok} {mask_ok}'],
                stdout=DEVNULL,
                stderr=DEVNULL,
                check=False,
            )
            kept4.append(rname)
        if kept4:
            run(
                ['sysrc', f'static_routes={" ".join(kept4)}'],
                stdout=DEVNULL,
                stderr=DEVNULL,
                check=False,
            )
        elif cur4:
            run(['sysrc', '-x', 'static_routes'], stdout=DEVNULL, stderr=DEVNULL, check=False)

        # IPv6 ipv6_static_routes
        res6 = run(
            ['sysrc', '-n', 'ipv6_static_routes'],
            stdout=PIPE,
            stderr=DEVNULL,
            universal_newlines=True,
            check=False,
        )
        cur6 = (res6.stdout or '').strip().split() if res6.returncode == 0 else []
        prefix6 = f'nm6_{rc_nic}_'
        kept6 = []
        for tok in cur6:
            if tok.startswith(prefix6):
                run(
                    ['sysrc', '-x', f'ipv6_route_{tok}'],
                    stdout=DEVNULL,
                    stderr=DEVNULL,
                    check=False,
                )
            else:
                kept6.append(tok)
        for idx, (net6_ok, plen_ok, gw6_ok) in enumerate(valid_r6):
            rname6 = f'{prefix6}{idx}'
            run(
                ['sysrc', f'ipv6_route_{rname6}={net6_ok}/{plen_ok} {gw6_ok}'],
                stdout=DEVNULL,
                stderr=DEVNULL,
                check=False,
            )
            kept6.append(rname6)
        if kept6:
            run(
                ['sysrc', f'ipv6_static_routes={" ".join(kept6)}'],
                stdout=DEVNULL,
                stderr=DEVNULL,
                check=False,
            )
        elif cur6:
            run(
                ['sysrc', '-x', 'ipv6_static_routes'],
                stdout=DEVNULL,
                stderr=DEVNULL,
                check=False,
            )
    except OSError:
        pass


def save_interface_routes(nic, ipv4_routes, ipv6_routes, target_dir=INTERFACE_ROUTES_DIR):
    """Persist validated IPv4 and IPv6 static routes for `nic`."""
    if not nic:
        return
    rc_nic = validate.rc_conf_interface(nic)
    old_r4, old_r6 = load_interface_routes(nic, target_dir=target_dir)
    os.makedirs(target_dir, exist_ok=True)
    try:
        os.chmod(target_dir, 0o700)
    except OSError:
        pass
    lines = [f'# Static routes for {rc_nic}']
    valid_r4 = []
    for rt in ipv4_routes or []:
        net = (rt.get('network') or '').strip()
        mask = (rt.get('netmask') or '').strip()
        gw = (rt.get('gateway') or '').strip()
        if net and mask and gw:
            net_ok = validate.ipv4_address(net, 'Static Route Network')
            mask_ok = validate.ipv4_netmask(mask)
            gw_ok = validate.ipv4_address(gw, 'Static Route Gateway')
            valid_r4.append((net_ok, mask_ok, gw_ok))
            lines.append(f'ipv4_route = {net_ok},{mask_ok},{gw_ok}')
    valid_r6 = []
    for rt6 in ipv6_routes or []:
        net6 = (rt6.get('network') or '').strip()
        plen = (rt6.get('prefixlen') or '64').strip().lstrip('/')
        gw6 = (rt6.get('gateway') or '').strip()
        if net6 and gw6:
            net6_ok = validate.ipv6_address(net6.split('/')[0], 'IPv6 Static Route Prefix')
            plen_ok = validate.ipv6_prefixlen(plen)
            gw6_ok = validate.ipv6_address(gw6, 'IPv6 Static Route Gateway', allow_scope=True)
            valid_r6.append((net6_ok, plen_ok, gw6_ok))
            lines.append(f'ipv6_route = {net6_ok},{plen_ok},{gw6_ok}')
    lines.append('')
    path = os.path.join(target_dir, f'{rc_nic}.routes')
    if os.path.islink(path):
        raise ValueError(f'Refusing to write to symlink: {path}')
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))

    new_r4_set = set(valid_r4)
    new_r6_set = set(valid_r6)
    removed_r4 = [
        r for r in old_r4
        if (r.get('network'), r.get('netmask'), r.get('gateway')) not in new_r4_set
    ]
    removed_r6 = [
        r for r in old_r6
        if (r.get('network'), r.get('prefixlen'), r.get('gateway')) not in new_r6_set
    ]
    _PENDING_REMOVED_ROUTES[rc_nic] = (removed_r4, removed_r6)

    if target_dir == INTERFACE_ROUTES_DIR:
        _sync_rc_conf_routes(rc_nic, valid_r4, valid_r6)


def apply_interface_routes(
    nic, ipv4_routes, ipv6_routes, old_ipv4_routes=None, old_ipv6_routes=None
):
    """Apply validated IPv4 and IPv6 static routes for `nic` to the live routing table."""
    rc_nic = validate.rc_conf_interface(nic) if nic else ''
    pending_r4, pending_r6 = _PENDING_REMOVED_ROUTES.pop(rc_nic, ([], []))
    del_r4 = old_ipv4_routes if old_ipv4_routes is not None else pending_r4
    del_r6 = old_ipv6_routes if old_ipv6_routes is not None else pending_r6

    for rt in del_r4 or []:
        net = (rt.get('network') or '').strip()
        mask = (rt.get('netmask') or '').strip()
        gw = (rt.get('gateway') or '').strip()
        if net and mask and gw:
            try:
                net_ok = validate.ipv4_address(net, 'Static Route Network')
                mask_ok = validate.ipv4_netmask(mask)
                gw_ok = validate.ipv4_address(gw, 'Static Route Gateway')
                run(
                    ['route', '-n', 'delete', '-net', net_ok, gw_ok, mask_ok],
                    stderr=DEVNULL,
                    check=False,
                )
            except ValueError:
                pass
    for rt6 in del_r6 or []:
        net6 = (rt6.get('network') or '').strip()
        plen = (rt6.get('prefixlen') or '64').strip().lstrip('/')
        gw6 = (rt6.get('gateway') or '').strip()
        if net6 and gw6:
            try:
                net6_ok = validate.ipv6_address(net6.split('/')[0], 'IPv6 Static Route Prefix')
                plen_ok = validate.ipv6_prefixlen(plen)
                gw6_ok = validate.ipv6_address(gw6, 'IPv6 Static Route Gateway', allow_scope=True)
                run(
                    ['route', '-n', 'delete', '-inet6', f'{net6_ok}/{plen_ok}', gw6_ok],
                    stderr=DEVNULL,
                    check=False,
                )
            except ValueError:
                pass

    for rt in ipv4_routes or []:
        net = (rt.get('network') or '').strip()
        mask = (rt.get('netmask') or '').strip()
        gw = (rt.get('gateway') or '').strip()
        if net and mask and gw:
            try:
                net_ok = validate.ipv4_address(net, 'Static Route Network')
                mask_ok = validate.ipv4_netmask(mask)
                gw_ok = validate.ipv4_address(gw, 'Static Route Gateway')
                run(
                    ['route', '-n', 'add', '-net', net_ok, gw_ok, mask_ok],
                    stderr=DEVNULL,
                    check=False,
                )
            except ValueError:
                pass
    for rt6 in ipv6_routes or []:
        net6 = (rt6.get('network') or '').strip()
        plen = (rt6.get('prefixlen') or '64').strip().lstrip('/')
        gw6 = (rt6.get('gateway') or '').strip()
        if net6 and gw6:
            try:
                net6_ok = validate.ipv6_address(net6.split('/')[0], 'IPv6 Static Route Prefix')
                plen_ok = validate.ipv6_prefixlen(plen)
                gw6_ok = validate.ipv6_address(gw6, 'IPv6 Static Route Gateway', allow_scope=True)
                run(
                    ['route', '-n', 'add', '-inet6', f'{net6_ok}/{plen_ok}', gw6_ok],
                    stderr=DEVNULL,
                    check=False,
                )
            except ValueError:
                pass


class NetCardConfigWindow(Gtk.Window):
    """The configuration window for one network interface."""

    def edit_ipv4_setting(self, widget):
        """Switch the IPv4 tab between DHCP and manual entry.

        Args:
            widget (Gtk.RadioButton): the radio button that changed. Ignored
                unless it is the one that became active.
        """
        if widget.get_active():
            self.method = widget.get_label()
            if self.method == "DHCP":
                self.ip_input_address_entry.set_sensitive(False)
                self.ip_input_mask_entry.set_sensitive(False)
                self.ip_input_gateway_entry.set_sensitive(False)
                self.prymary_dns_entry.set_sensitive(False)
                self.secondary_dns_entry.set_sensitive(False)
                self.search_entry.set_sensitive(False)
            else:
                self.ip_input_address_entry.set_sensitive(True)
                self.ip_input_mask_entry.set_sensitive(True)
                self.ip_input_gateway_entry.set_sensitive(True)
                self.prymary_dns_entry.set_sensitive(True)
                self.secondary_dns_entry.set_sensitive(True)
                self.search_entry.set_sensitive(True)
            if self.method == self.current_settings["Assignment Method"]:
                self.save_button.set_sensitive(False)
            else:
                self.save_button.set_sensitive(self.settings_complete())

    def edit_ipv6_setting(self, widget, value):
        """Switch the IPv6 tab between SLAAC and manual entry.

        Args:
            widget (Gtk.RadioButton): the radio button that changed. Ignored
                unless it is the one that became active.
            value (str): the method the button stands for, "SLAAC" or
                "Manual".
        """
        if widget.get_active():
            self.method6 = value
            # Check if GUI elements exist (may be called during init)
            if not hasattr(self, 'ip_input_address_entry6'):
                return
            if value == "SLAAC":
                self.ip_input_address_entry6.set_sensitive(False)
                self.ip_input_mask_entry6.set_sensitive(False)
                self.ip_input_gateway_entry6.set_sensitive(False)
                self.prymary_dns_entry6.set_sensitive(False)
                self.search_entry6.set_sensitive(False)
            else:
                self.ip_input_address_entry6.set_sensitive(True)
                self.ip_input_mask_entry6.set_sensitive(True)
                self.ip_input_gateway_entry6.set_sensitive(True)
                self.prymary_dns_entry6.set_sensitive(True)
                self.search_entry6.set_sensitive(True)
            # Enable save button if method changed
            if self.method6 == self.current_settings6["Assignment Method"]:
                self.save_button.set_sensitive(False)
            else:
                self.save_button.set_sensitive(self.settings_complete())

    def settings_complete(self):
        """Report whether the entries hold enough to save.

        Returns:
            bool: False when the IPv4 method is Manual with no primary DNS
                server, or the IPv6 method is Manual with no address.
        """
        if self.method == 'Manual' and not self.prymary_dns_entry.get_text().strip():
            return False
        if self.method6 == 'Manual' and not self.ip_input_address_entry6.get_text().strip():
            return False
        return True

    def entry_trigger_save_button(self, _widget, _event):
        """Enable Save as soon as the user edits any entry.

        Args:
            _widget (Gtk.Widget): the edited entry, unused.
            _event (Gdk.Event): the key event, unused.
        """
        self.save_button.set_sensitive(self.settings_complete())

    def __init__(self, selected_nic=None, on_saved=None):
        # Build Default Window
        Gtk.Window.__init__(self, title="Network Configuration")
        self.set_default_size(580, 520)
        self.on_saved = on_saved
        self.nics = nics_list()
        # The checked values Save hands to update_system().
        self.pending = {}
        default_nic = selected_nic if selected_nic else default_card()
        self.active_nic = default_nic
        # Build Tab 1 Content
        # Interface Drop Down Combo Box
        cell = Gtk.CellRendererText()

        interface_combo_box = Gtk.ComboBox()
        interface_combo_box.pack_start(cell, expand=True)
        interface_combo_box.add_attribute(cell, 'text', 0)

        # Add interfaces to a ListStore
        store = Gtk.ListStore(str)

        for nic in self.nics:
            store.append([nic])

        interface_combo_box.set_model(store)
        interface_combo_box.set_margin_top(15)
        interface_combo_box.set_margin_end(30)
        if default_nic:
            active_index = self.nics.index(f"{default_nic}")
            interface_combo_box.set_active(active_index)
        self.current_settings = get_interface_settings(default_nic)
        self.method = self.current_settings["Assignment Method"]
        # IPv6 settings
        self.current_settings6 = get_interface_settings_ipv6(default_nic)
        self.method6 = self.current_settings6["Assignment Method"]
        interface_combo_box.connect("changed", self.cbox_config_refresh)

        # Build Label to sit in front of the ComboBox
        label_one = Gtk.Label(label="Interface:")
        label_one.set_margin_top(15)
        label_one.set_margin_start(30)

        # Add both objects to a single box, which will then be added to the grid
        interface_box = Gtk.Box(orientation=0, spacing=100)
        interface_box.pack_start(label_one, False, False, 0)
        interface_box.pack_end(interface_combo_box, True, True, 0)

        # Add radio button to toggle DHCP or not
        self.rb_dhcp4 = Gtk.RadioButton.new_with_label(None, "DHCP")
        self.rb_dhcp4.set_margin_top(15)
        self.rb_manual4 = Gtk.RadioButton.new_with_label_from_widget(
            self.rb_dhcp4, "Manual")
        self.rb_manual4.set_margin_top(15)
        if self.current_settings["Assignment Method"] == "DHCP":
            self.rb_dhcp4.set_active(True)
        else:
            self.rb_manual4.set_active(True)
        self.rb_manual4.join_group(self.rb_dhcp4)

        radio_button_label = Gtk.Label(label="IPv4 Method:")
        radio_button_label.set_margin_top(15)
        radio_button_label.set_margin_start(30)

        radio_box = Gtk.Box(orientation=0, spacing=50)
        radio_box.set_homogeneous(False)
        radio_box.pack_start(radio_button_label, False, False, 0)
        radio_box.pack_start(self.rb_dhcp4, True, False, 0)
        radio_box.pack_end(self.rb_manual4, True, True, 0)

        # Add Manual Address Field
        ip_input_address_label = Gtk.Label(label="Address")
        ip_input_address_label.set_margin_top(15)

        ip_input_mask_label = Gtk.Label(label="Subnet Mask")
        ip_input_mask_label.set_margin_top(15)

        ip_input_gateway_label = Gtk.Label(label="Gateway")
        ip_input_gateway_label.set_margin_top(15)

        self.ip_input_address_entry = Gtk.Entry()
        self.ip_input_address_entry.set_margin_start(15)
        self.ip_input_address_entry.set_text(self.current_settings["Interface IP"])
        self.ip_input_address_entry.connect("key-release-event", self.entry_trigger_save_button)

        self.ip_input_mask_entry = Gtk.Entry()
        self.ip_input_mask_entry.set_text(self.current_settings["Interface Subnet Mask"])
        self.ip_input_mask_entry.connect("key-release-event", self.entry_trigger_save_button)

        self.ip_input_gateway_entry = Gtk.Entry()
        self.ip_input_gateway_entry.set_margin_end(15)
        self.ip_input_gateway_entry.set_text(self.current_settings["Default Gateway"])
        self.ip_input_gateway_entry.connect("key-release-event", self.entry_trigger_save_button)

        ip_input_box = Gtk.Box(orientation=0, spacing=0)
        ip_input_box.set_homogeneous(True)
        ip_input_box.pack_start(ip_input_address_label, False, False, 0)
        ip_input_box.pack_start(ip_input_mask_label, False, False, 0)
        ip_input_box.pack_start(ip_input_gateway_label, False, False, 0)

        ip_entry_box = Gtk.Box(orientation=0, spacing=30)
        ip_entry_box.pack_start(self.ip_input_address_entry, False, False, 0)
        ip_entry_box.pack_start(self.ip_input_mask_entry, False, False, 0)
        ip_entry_box.pack_start(self.ip_input_gateway_entry, False, False, 0)

        # Add DNS Server Settings
        prymary_dns_label = Gtk.Label(label="Primary DNS Servers: ")
        prymary_dns_label.set_margin_top(15)
        prymary_dns_label.set_margin_end(58)
        prymary_dns_label.set_margin_start(30)

        secondary_dns_label = Gtk.Label(label="Secondary DNS Servers: ")
        secondary_dns_label.set_margin_top(15)
        secondary_dns_label.set_margin_end(58)
        secondary_dns_label.set_margin_start(30)

        self.prymary_dns_entry = Gtk.Entry()
        self.prymary_dns_entry.set_margin_end(30)
        self.prymary_dns_entry.set_text(self.current_settings["DNS Server 1"])
        self.prymary_dns_entry.connect("key-release-event", self.entry_trigger_save_button)

        self.secondary_dns_entry = Gtk.Entry()
        self.secondary_dns_entry.set_margin_end(30)
        self.secondary_dns_entry.set_text(self.current_settings["DNS Server 2"])
        self.secondary_dns_entry.connect("key-release-event", self.entry_trigger_save_button)

        dns_entry_box1 = Gtk.Box(orientation=0, spacing=0)
        dns_entry_box1.pack_start(prymary_dns_label, False, False, 0)

        dns_entry_box1.pack_end(self.prymary_dns_entry, True, True, 0)

        dns_entry_box2 = Gtk.Box(orientation=0, spacing=0)
        dns_entry_box2.pack_start(secondary_dns_label, False, False, 0)

        dns_entry_box2.pack_end(self.secondary_dns_entry, True, True, 0)

        # Add Search Domain Settings
        search_label = Gtk.Label(label="Search domains: ")
        search_label.set_margin_top(15)
        search_label.set_margin_end(30)
        search_label.set_margin_start(30)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_margin_top(21)
        self.search_entry.set_margin_end(30)
        self.search_entry.set_margin_bottom(30)
        self.search_entry.set_text(self.current_settings["Search Domain"])
        self.search_entry.connect("key-release-event", self.entry_trigger_save_button)

        search_box = Gtk.Box(orientation=0, spacing=0)
        search_box.pack_start(search_label, False, False, 0)
        search_box.pack_end(self.search_entry, True, True, 0)

        self.rb_dhcp4.connect("toggled", self.edit_ipv4_setting)
        self.rb_manual4.connect("toggled", self.edit_ipv4_setting)

        if self.current_settings["Assignment Method"] == "DHCP":
            self.ip_input_address_entry.set_sensitive(False)
            self.ip_input_mask_entry.set_sensitive(False)
            self.ip_input_gateway_entry.set_sensitive(False)
            self.prymary_dns_entry.set_sensitive(False)
            self.secondary_dns_entry.set_sensitive(False)
            self.search_entry.set_sensitive(False)

        routes_box4 = self._build_nic_ipv4_routes_section()

        grid_one = Gtk.Grid()
        grid_one.set_column_homogeneous(True)
        grid_one.set_row_homogeneous(False)
        grid_one.set_column_spacing(5)
        grid_one.set_row_spacing(10)
        grid_one.attach(interface_box, 0, 0, 4, 1)
        grid_one.attach(radio_box, 0, 1, 4, 1)
        grid_one.attach(ip_input_box, 0, 2, 4, 1)
        grid_one.attach(ip_entry_box, 0, 3, 4, 1)
        grid_one.attach(dns_entry_box1, 0, 4, 4, 1)
        grid_one.attach(dns_entry_box2, 0, 5, 4, 1)
        grid_one.attach(search_box, 0, 6, 4, 1)
        grid_one.attach(routes_box4, 0, 7, 4, 1)

        # Build Tab 2 Content

        # Interface Drop Down Combo Box
        cell6 = Gtk.CellRendererText()

        interface_combo_box6 = Gtk.ComboBox()
        interface_combo_box6.pack_start(cell6, expand=True)
        interface_combo_box6.add_attribute(cell6, 'text', 0)

        # Add interfaces to a ListStore
        store6 = Gtk.ListStore(str)
        for validinterface6 in self.nics:
            store6.append([validinterface6])

        interface_combo_box6.set_model(store6)
        interface_combo_box6.set_margin_top(15)
        interface_combo_box6.set_margin_end(30)

        if default_nic:
            active_combo_box_object_index6 = self.nics.index(f"{default_nic}")
            interface_combo_box6.set_active(active_combo_box_object_index6)
        interface_combo_box6.connect("changed", self.cbox_config_refresh)

        # Build Label to sit in front of the ComboBox
        label_one6 = Gtk.Label(label="Interface:")
        label_one6.set_margin_top(15)
        label_one6.set_margin_start(30)

        # Add both objects to a single box, which will then be added to the grid
        interface_box6 = Gtk.Box(orientation=0, spacing=100)
        interface_box6.pack_start(label_one6, False, False, 0)
        interface_box6.pack_end(interface_combo_box6, True, True, 0)

        # Add radio button to toggle SLAAC or Manual
        self.rb_slaac6 = Gtk.RadioButton.new_with_label(None, "SLAAC")
        self.rb_slaac6.set_margin_top(15)
        self.rb_slaac6.connect("toggled", self.edit_ipv6_setting, "SLAAC")
        self.rb_manual6 = Gtk.RadioButton.new_with_label_from_widget(
            self.rb_slaac6, "Manual")
        self.rb_manual6.set_margin_top(15)
        self.rb_manual6.join_group(self.rb_slaac6)
        self.rb_manual6.connect("toggled", self.edit_ipv6_setting, "Manual")

        # Set initial state based on current settings
        if self.method6 == "Manual":
            self.rb_manual6.set_active(True)
        else:
            self.rb_slaac6.set_active(True)

        radio_button_label6 = Gtk.Label(label="IPv6 Method:")
        radio_button_label6.set_margin_top(15)
        radio_button_label6.set_margin_start(30)

        radio_box6 = Gtk.Box(orientation=0, spacing=50)
        radio_box6.set_homogeneous(False)
        radio_box6.pack_start(radio_button_label6, False, False, 0)
        radio_box6.pack_start(self.rb_slaac6, True, False, 0)
        radio_box6.pack_end(self.rb_manual6, True, True, 0)

        # Add Manual Address Field
        ip_input_address_label6 = Gtk.Label(label="Address")
        ip_input_address_label6.set_margin_top(15)

        ip_input_mask_label6 = Gtk.Label(label="Prefix Length")
        ip_input_mask_label6.set_margin_top(15)

        ip_input_gateway_label6 = Gtk.Label(label="Gateway")
        ip_input_gateway_label6.set_margin_top(15)

        self.ip_input_address_entry6 = Gtk.Entry()
        self.ip_input_address_entry6.set_margin_start(15)
        self.ip_input_address_entry6.connect("key-release-event", self.entry_trigger_save_button)
        self.ip_input_mask_entry6 = Gtk.Entry()
        self.ip_input_mask_entry6.connect("key-release-event", self.entry_trigger_save_button)
        self.ip_input_gateway_entry6 = Gtk.Entry()
        self.ip_input_gateway_entry6.set_margin_end(15)
        self.ip_input_gateway_entry6.connect("key-release-event", self.entry_trigger_save_button)

        ip_input_box6 = Gtk.Box(orientation=0, spacing=0)
        ip_input_box6.set_homogeneous(True)
        ip_input_box6.pack_start(ip_input_address_label6, False, False, 0)
        ip_input_box6.pack_start(ip_input_mask_label6, False, False, 0)
        ip_input_box6.pack_start(ip_input_gateway_label6, False, False, 0)

        ip_entry_box6 = Gtk.Box(orientation=0, spacing=30)
        ip_entry_box6.pack_start(self.ip_input_address_entry6, False, False, 0)
        ip_entry_box6.pack_start(self.ip_input_mask_entry6, False, False, 0)
        ip_entry_box6.pack_start(self.ip_input_gateway_entry6, False, False, 0)

        # Add DNS Server Settings
        prymary_dns_label6 = Gtk.Label(label="Primary DNS Servers: ")
        prymary_dns_label6.set_margin_top(15)
        prymary_dns_label6.set_margin_end(58)
        prymary_dns_label6.set_margin_start(30)

        secondary_dns_label6 = Gtk.Label(label="Secondary DNS Servers: ")
        secondary_dns_label6.set_margin_top(15)
        secondary_dns_label6.set_margin_end(58)
        secondary_dns_label6.set_margin_start(30)

        self.prymary_dns_entry6 = Gtk.Entry()
        self.prymary_dns_entry6.set_margin_end(30)
        self.prymary_dns_entry6.connect("key-release-event", self.entry_trigger_save_button)

        dns_entry_box6 = Gtk.Box(orientation=0, spacing=0)
        dns_entry_box6.pack_start(prymary_dns_label6, False, False, 0)
        dns_entry_box6.pack_end(self.prymary_dns_entry6, True, True, 0)

        # Add Search Domain Settings

        search_label6 = Gtk.Label(label="Search domains: ")
        search_label6.set_margin_top(15)
        search_label6.set_margin_end(30)
        search_label6.set_margin_start(30)

        self.search_entry6 = Gtk.Entry()
        self.search_entry6.set_margin_top(21)
        self.search_entry6.set_margin_end(30)
        self.search_entry6.set_margin_bottom(30)
        self.search_entry6.connect("key-release-event", self.entry_trigger_save_button)

        search_box6 = Gtk.Box(orientation=0, spacing=0)
        search_box6.pack_start(search_label6, False, False, 0)
        search_box6.pack_end(self.search_entry6, True, True, 0)

        # Set initial sensitivity based on current method (SLAAC = disabled, Manual = enabled)
        manual_enabled = self.method6 == "Manual"
        self.ip_input_address_entry6.set_sensitive(manual_enabled)
        self.ip_input_mask_entry6.set_sensitive(manual_enabled)
        self.ip_input_gateway_entry6.set_sensitive(manual_enabled)
        self.prymary_dns_entry6.set_sensitive(manual_enabled)
        self.search_entry6.set_sensitive(manual_enabled)

        routes_box6 = self._build_nic_ipv6_routes_section()
        self._reload_nic_routes(default_nic)

        grid_one6 = Gtk.Grid()
        grid_one6.set_column_homogeneous(True)
        grid_one6.set_row_homogeneous(False)
        grid_one6.set_column_spacing(5)
        grid_one6.set_row_spacing(10)
        grid_one6.attach(interface_box6, 0, 0, 4, 1)
        grid_one6.attach(radio_box6, 0, 1, 4, 1)
        grid_one6.attach(ip_input_box6, 0, 2, 4, 1)
        grid_one6.attach(ip_entry_box6, 0, 3, 4, 1)
        grid_one6.attach(dns_entry_box6, 0, 4, 4, 1)
        grid_one6.attach(search_box6, 0, 5, 4, 1)
        grid_one6.attach(routes_box6, 0, 6, 4, 1)

        # Build Notebook

        nb = Gtk.Notebook()
        nb.set_margin_start(10)
        nb.set_margin_end(10)
        nb.set_margin_top(10)
        nb.set_margin_bottom(10)
        nb.set_tab_pos(2)
        # nb.set_sensitive(False)
        # Build Save & Cancel Buttons

        self.save_button = Gtk.Button(label="Save")
        self.save_button.set_margin_bottom(10)
        self.save_button.set_margin_start(10)
        self.save_button.connect("clicked", self.commit_pending_changes)
        self.save_button.set_sensitive(False)
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.set_margin_bottom(10)
        cancel_button.connect("clicked", self.discard_pending_changes)
        buttons_window = Gtk.Box(orientation=0, spacing=10)
        buttons_window.pack_start(self.save_button, False, False, 0)
        buttons_window.pack_start(cancel_button, False, False, 0)

        # Apply Tab 1 content and formatting to the notebook
        nb.append_page(grid_one)
        nb.set_tab_label_text(grid_one, "IPv4 Settings")

        # Apply Tab 2 content and formatting to the notebook
        nb.append_page(grid_one6)
        nb.set_tab_label_text(grid_one6, "IPv6 Settings")

        # Apply Tab 3 (VPN Settings) to the notebook
        vpn_tab = self._build_vpn_tab()
        nb.append_page(vpn_tab)
        nb.set_tab_label_text(vpn_tab, "VPN Settings")

        # Put all the widgets together into one window
        main_box = Gtk.Box(orientation=1, spacing=0)
        main_box.pack_start(nb, True, True, 0)
        main_box.pack_end(buttons_window, False, False, 0)
        self.add(main_box)

    def _build_nic_ipv4_routes_section(self):
        """Build the IPv4 Static Routes table and quick-add controls for an interface."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        vbox.set_margin_bottom(10)

        lbl = Gtk.Label(label="Static Routes (IPv4):")
        lbl.set_halign(Gtk.Align.START)
        vbox.pack_start(lbl, False, False, 0)

        self.nic_r4_store = Gtk.ListStore(str, str, str)
        self.nic_r4_tree = Gtk.TreeView(model=self.nic_r4_store)
        for idx, (col_title, width) in enumerate(
            (("Destination Network", 150), ("Subnet Mask", 140), ("Gateway", 140))
        ):
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(col_title, renderer, text=idx)
            col.set_min_width(width)
            col.set_resizable(True)
            self.nic_r4_tree.append_column(col)

        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(80)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.nic_r4_tree)
        vbox.pack_start(scroll, True, True, 0)

        add_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.nic_r4_net = Gtk.Entry()
        self.nic_r4_net.set_placeholder_text("Network (10.8.0.0)")
        self.nic_r4_mask = Gtk.Entry()
        self.nic_r4_mask.set_placeholder_text("Mask (255.255.255.0)")
        self.nic_r4_gw = Gtk.Entry()
        self.nic_r4_gw.set_placeholder_text("Gateway (192.168.1.1)")

        add_btn = Gtk.Button(label="Add Route")
        add_btn.connect("clicked", self._on_add_nic_r4)
        del_btn = Gtk.Button(label="Remove")
        del_btn.connect("clicked", self._on_del_nic_r4)

        add_bar.pack_start(self.nic_r4_net, True, True, 0)
        add_bar.pack_start(self.nic_r4_mask, True, True, 0)
        add_bar.pack_start(self.nic_r4_gw, True, True, 0)
        add_bar.pack_start(add_btn, False, False, 0)
        add_bar.pack_start(del_btn, False, False, 0)
        vbox.pack_start(add_bar, False, False, 0)
        return vbox

    def _on_add_nic_r4(self, _widget):
        net = self.nic_r4_net.get_text().strip()
        mask = self.nic_r4_mask.get_text().strip() or '255.255.255.0'
        gw = self.nic_r4_gw.get_text().strip()
        if net and gw:
            self.nic_r4_store.append([net, mask, gw])
            self.nic_r4_net.set_text('')
            self.nic_r4_mask.set_text('')
            self.nic_r4_gw.set_text('')
            self.save_button.set_sensitive(self.settings_complete())

    def _on_del_nic_r4(self, _widget):
        sel = self.nic_r4_tree.get_selection()
        model, it = sel.get_selected()
        if it is not None:
            model.remove(it)
            self.save_button.set_sensitive(self.settings_complete())

    def _build_nic_ipv6_routes_section(self):
        """Build the IPv6 Static Routes table and quick-add controls for an interface."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        vbox.set_margin_bottom(10)

        lbl = Gtk.Label(label="Static Routes (IPv6):")
        lbl.set_halign(Gtk.Align.START)
        vbox.pack_start(lbl, False, False, 0)

        self.nic_r6_store = Gtk.ListStore(str, str, str)
        self.nic_r6_tree = Gtk.TreeView(model=self.nic_r6_store)
        for idx, (col_title, width) in enumerate(
            (("Destination Prefix", 170), ("Prefix Length", 100), ("Gateway", 160))
        ):
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(col_title, renderer, text=idx)
            col.set_min_width(width)
            col.set_resizable(True)
            self.nic_r6_tree.append_column(col)

        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(80)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.nic_r6_tree)
        vbox.pack_start(scroll, True, True, 0)

        add_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.nic_r6_net = Gtk.Entry()
        self.nic_r6_net.set_placeholder_text("Prefix (fd00:10::)")
        self.nic_r6_plen = Gtk.Entry()
        self.nic_r6_plen.set_placeholder_text("64")
        self.nic_r6_plen.set_width_chars(6)
        self.nic_r6_gw = Gtk.Entry()
        self.nic_r6_gw.set_placeholder_text("Gateway (fd00::1)")

        add_btn = Gtk.Button(label="Add Route")
        add_btn.connect("clicked", self._on_add_nic_r6)
        del_btn = Gtk.Button(label="Remove")
        del_btn.connect("clicked", self._on_del_nic_r6)

        add_bar.pack_start(self.nic_r6_net, True, True, 0)
        add_bar.pack_start(self.nic_r6_plen, False, False, 0)
        add_bar.pack_start(self.nic_r6_gw, True, True, 0)
        add_bar.pack_start(add_btn, False, False, 0)
        add_bar.pack_start(del_btn, False, False, 0)
        vbox.pack_start(add_bar, False, False, 0)
        return vbox

    def _on_add_nic_r6(self, _widget):
        net = self.nic_r6_net.get_text().strip()
        plen = self.nic_r6_plen.get_text().strip() or '64'
        gw = self.nic_r6_gw.get_text().strip()
        if net and gw:
            self.nic_r6_store.append([net, plen, gw])
            self.nic_r6_net.set_text('')
            self.nic_r6_plen.set_text('')
            self.nic_r6_gw.set_text('')
            self.save_button.set_sensitive(self.settings_complete())

    def _on_del_nic_r6(self, _widget):
        sel = self.nic_r6_tree.get_selection()
        model, it = sel.get_selected()
        if it is not None:
            model.remove(it)
            self.save_button.set_sensitive(self.settings_complete())

    def _reload_nic_routes(self, nic):
        """Populate the IPv4 and IPv6 Static Routes stores for `nic`."""
        if hasattr(self, 'nic_r4_store'):
            self.nic_r4_store.clear()
        if hasattr(self, 'nic_r6_store'):
            self.nic_r6_store.clear()
        r4_list, r6_list = load_interface_routes(nic)
        for rt in r4_list:
            self.nic_r4_store.append([rt['network'], rt['netmask'], rt['gateway']])
        for rt6 in r6_list:
            self.nic_r6_store.append([rt6['network'], rt6['prefixlen'], rt6['gateway']])

    # Used with the combo box to refresh the UI of tab 1 with active settings
    # for the newly selected active interface.
    def cbox_config_refresh(self, widget):
        """Reload both tabs for the interface just chosen in the combo box.

        Args:
            widget (Gtk.ComboBox): the interface combo box.
        """
        selected_nic = self.nics[widget.get_active()]
        self.active_nic = selected_nic
        self.current_settings = get_interface_settings(selected_nic)
        self.current_settings6 = get_interface_settings_ipv6(selected_nic)
        self.update_interface_settings()
        self.update_interface_settings_ipv6()
        self._reload_nic_routes(selected_nic)

    def update_interface_settings(self):
        """Fill the IPv4 tab's widgets from the current settings."""
        self.ip_input_address_entry.set_text(self.current_settings["Interface IP"])
        self.ip_input_mask_entry.set_text(self.current_settings["Interface Subnet Mask"])
        self.ip_input_gateway_entry.set_text(self.current_settings["Default Gateway"])
        self.prymary_dns_entry.set_text(self.current_settings["DNS Server 1"])
        self.secondary_dns_entry.set_text(self.current_settings["DNS Server 2"])
        self.search_entry.set_text(self.current_settings["Search Domain"])
        if self.current_settings["Assignment Method"] == "DHCP":
            self.rb_dhcp4.set_active(True)
        else:
            self.rb_manual4.set_active(True)

    def update_interface_settings_ipv6(self):
        """Fill the IPv6 tab's widgets from the current settings."""
        self.ip_input_address_entry6.set_text(self.current_settings6.get("Interface IPv6", ""))
        self.ip_input_mask_entry6.set_text(str(self.current_settings6.get("Prefix Length", "64")))
        self.ip_input_gateway_entry6.set_text(self.current_settings6.get("Default Gateway", ""))
        self.prymary_dns_entry6.set_text(self.current_settings6.get("DNS Server 1", ""))
        self.search_entry6.set_text(self.current_settings6.get("Search Domain", ""))
        self.method6 = self.current_settings6.get("Assignment Method", "SLAAC")
        if self.method6 == "Manual":
            self.rb_manual6.set_active(True)
            self.ip_input_address_entry6.set_sensitive(True)
            self.ip_input_mask_entry6.set_sensitive(True)
            self.ip_input_gateway_entry6.set_sensitive(True)
            self.prymary_dns_entry6.set_sensitive(True)
            self.search_entry6.set_sensitive(True)
        else:
            self.rb_slaac6.set_active(True)
            self.ip_input_address_entry6.set_sensitive(False)
            self.ip_input_mask_entry6.set_sensitive(False)
            self.ip_input_gateway_entry6.set_sensitive(False)
            self.prymary_dns_entry6.set_sensitive(False)
            self.search_entry6.set_sensitive(False)

    def commit_pending_changes(self, _widget):
        """Check the entries, then apply them on the GTK idle handler.

        When an entry is invalid, an error dialog names it and the window
        stays open so it can be corrected. Nothing is written.

        Args:
            _widget (Gtk.Widget): the Save button, unused.
        """
        if hasattr(self, 'nic_r4_net') and self.nic_r4_net.get_text().strip():
            self._on_add_nic_r4(None)
        if hasattr(self, 'nic_r6_net') and self.nic_r6_net.get_text().strip():
            self._on_add_nic_r6(None)
        try:
            self.pending = self.validated_settings()
        except ValueError as error:
            self.show_invalid_entry(str(error))
            return
        self.hide_window()
        GLib.idle_add(self.update_system)

    def validated_settings(self):
        """Read the entries the chosen methods use and check each of them.

        Returns:
            dict[str, str]: the interface and the normalized values, keyed
                nic, inet, netmask, defaultrouter, dns1, dns2, search,
                inet6, prefixlen, gateway6 and dns6. Optional entries left
                blank are empty strings.

        Raises:
            ValueError: naming the first entry that is not valid.
        """
        nic = validate.interface(self.current_settings["Active Interface"])
        if nic not in self.nics:
            raise ValueError(f'"{nic}" is not one of this system\'s interfaces.')
        settings = {'nic': nic, 'inet': '', 'netmask': ''}
        if self.method == 'DHCP':
            # Saving DHCP briefly puts the current address back while
            # dhclient starts. The entries are greyed out and hold what
            # ifconfig reported, so an empty or odd value just skips that.
            try:
                settings['inet'] = validate.ipv4_address(
                    self.ip_input_address_entry.get_text(), 'Address')
                settings['netmask'] = validate.ipv4_netmask(
                    self.ip_input_mask_entry.get_text())
            except ValueError:
                settings['inet'] = settings['netmask'] = ''
        if self.method == 'Manual':
            gateway = self.ip_input_gateway_entry.get_text().strip()
            dns2 = self.secondary_dns_entry.get_text().strip()
            settings.update({
                'inet': validate.ipv4_address(
                    self.ip_input_address_entry.get_text(), 'Address'),
                'netmask': validate.ipv4_netmask(
                    self.ip_input_mask_entry.get_text()),
                'defaultrouter': validate.ipv4_address(gateway, 'Gateway')
                if gateway else '',
                'dns1': validate.ip_address(
                    self.prymary_dns_entry.get_text(), 'Primary DNS Server'),
                'dns2': validate.ip_address(dns2, 'Secondary DNS Server')
                if dns2 else '',
                'search': validate.search_domains(self.search_entry.get_text()),
            })
        if self.method6 == 'Manual':
            prefixlen = self.ip_input_mask_entry6.get_text().strip() or '64'
            gateway6 = self.ip_input_gateway_entry6.get_text().strip()
            dns6 = self.prymary_dns_entry6.get_text().strip()
            settings.update({
                'inet6': validate.ipv6_address(
                    self.ip_input_address_entry6.get_text(), 'IPv6 Address'),
                'prefixlen': validate.ipv6_prefixlen(prefixlen),
                'gateway6': validate.ipv6_address(
                    gateway6, 'IPv6 Gateway', allow_scope=True)
                if gateway6 else '',
                'dns6': validate.ipv6_address(dns6, 'IPv6 DNS Server')
                if dns6 else '',
            })
        scope = settings.get('gateway6', '').partition('%')[2]
        if scope and scope != nic:
            raise ValueError(
                f'IPv6 Gateway: the "%{scope}" zone does not match the '
                f'interface being configured, {nic}.')
        if hasattr(self, 'nic_r4_store'):
            for r in self.nic_r4_store:
                validate.ipv4_address(r[0], 'Static Route Network')
                validate.ipv4_netmask(r[1])
                validate.ipv4_address(r[2], 'Static Route Gateway')
        if hasattr(self, 'nic_r6_store'):
            for r6 in self.nic_r6_store:
                validate.ipv6_address(r6[0].split('/')[0], 'IPv6 Static Route Prefix')
                validate.ipv6_prefixlen(r6[1].lstrip('/'))
                validate.ipv6_address(r6[2], 'IPv6 Static Route Gateway', allow_scope=True)
        return settings

    def show_invalid_entry(self, message):
        """Tell the user which entry was refused.

        Args:
            message (str): the ValueError text from NetworkMgr.validate.
        """
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Invalid network setting",
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def update_system(self):
        """Write the chosen IPv4 and IPv6 settings and apply them.

        rc.conf is updated through sysrc, /etc/resolv.conf is rewritten for
        a manual configuration, and the interface is restarted so the new
        settings take effect straight away.
        """
        settings = self.pending
        nic = settings['nic']
        rc_nic = validate.rc_conf_interface(nic)
        if self.method == 'Manual':
            inet = settings['inet']
            netmask = settings['netmask']
            if 'wlan' in nic:
                ifconfig_value = f'WPA inet {inet} netmask {netmask}'
            else:
                ifconfig_value = f'inet {inet} netmask {netmask}'
            self.set_rc_conf(f'ifconfig_{rc_nic}', ifconfig_value)
            if settings['defaultrouter']:
                self.set_rc_conf('defaultrouter', settings['defaultrouter'])
            else:
                self.remove_rc_conf_var('defaultrouter')
            start_static_network(nic, inet, netmask)
            with open('/etc/resolv.conf', 'w', encoding='utf-8') as resolv_conf:
                resolv_conf.writelines('# Generated by NetworkMgr\n')
                search = settings['search']
                if search:
                    search_line = f'search {search}\n'
                    resolv_conf.writelines(search_line)
                dns1 = settings['dns1']
                nameserver1_line = f'nameserver {dns1}\n'
                resolv_conf.writelines(nameserver1_line)
                dns2 = settings['dns2']
                if dns2:
                    nameserver2_line = f'nameserver {dns2}\n'
                    resolv_conf.writelines(nameserver2_line)
        else:
            self.set_rc_conf(f'ifconfig_{rc_nic}',
                             'WPA DHCP' if 'wlan' in nic else 'DHCP')

            with open('/etc/rc.conf', 'r', encoding='utf-8') as rc_conf_file:
                rc_conf = rc_conf_file.read()
            for nic_search in self.nics:
                rc_search = validate.rc_conf_interface(nic_search)
                if re.search(f'^ifconfig_{rc_search}=".*inet', rc_conf, re.MULTILINE):
                    break
            else:
                # Nothing static left, so dhclient takes the default
                # route back.
                self.remove_rc_conf_var('defaultrouter')
            restart_card_network(nic)
            # sometimes the inet address isn't available immediately after dhcp is enabled.
            if settings['inet']:
                start_static_network(nic, settings['inet'], settings['netmask'])
            wait_for_address(nic)
            restart_routing_and_dhcp(nic)

        # Apply IPv6 configuration
        self.update_system_ipv6(settings)

        # Persist and apply static routes for this interface
        if hasattr(self, 'nic_r4_store') and hasattr(self, 'nic_r6_store'):
            r4_list = [
                {'network': r[0], 'netmask': r[1], 'gateway': r[2]}
                for r in self.nic_r4_store
            ]
            r6_list = [
                {'network': r[0], 'prefixlen': r[1], 'gateway': r[2]}
                for r in self.nic_r6_store
            ]
            save_interface_routes(nic, r4_list, r6_list)
            apply_interface_routes(nic, r4_list, r6_list)

        if self.on_saved is not None:
            self.on_saved()
        self.destroy()

    def update_system_ipv6(self, settings):
        """Apply IPv6 configuration changes.

        Args:
            settings (dict[str, str]): the checked values from
                validated_settings().
        """
        nic = settings['nic']
        rc_nic = validate.rc_conf_interface(nic)

        if self.method6 == 'Manual':
            inet6 = settings['inet6']
            prefixlen = settings['prefixlen']
            gateway6 = settings['gateway6']
            dns6 = settings['dns6']
            # Static IPv6 configuration
            self.set_rc_conf(f'ifconfig_{rc_nic}_ipv6',
                             f'inet6 {inet6} prefixlen {prefixlen}')

            # Disable rtsold for static configuration
            self.set_rc_conf('rtsold_enable', 'NO')

            # Apply the static IPv6 address
            if inet6:
                disable_slaac(nic)
                start_static_ipv6_network(nic, inet6, prefixlen)

            # Set IPv6 default gateway if provided
            if gateway6:
                # Link-local addresses (fe80::) need interface suffix
                if gateway6.lower().startswith('fe80:') and '%' not in gateway6:
                    gateway6_full = f'{gateway6}%{nic}'
                else:
                    gateway6_full = gateway6
                # Save with interface suffix in rc.conf for persistence
                self.set_rc_conf('ipv6_defaultrouter', gateway6_full)
                # Apply gateway immediately
                run(['route', 'delete', '-inet6', 'default'],
                    stderr=DEVNULL, check=False)
                run(['route', 'add', '-inet6', 'default', gateway6_full],
                    check=False)

            # Add IPv6 DNS to resolv.conf if provided
            if dns6:
                self.add_ipv6_dns(dns6)
        else:
            # SLAAC configuration
            self.set_rc_conf(f'ifconfig_{rc_nic}_ipv6', 'inet6 accept_rtadv')

            # Enable rtsold for SLAAC
            self.set_rc_conf('rtsold_enable', 'YES')

            # SLAAC supplies the gateway. sysrc -x on an unset variable
            # is harmless.
            self.remove_rc_conf_var('ipv6_defaultrouter')

            # Enable SLAAC
            enable_slaac(nic)

    def add_ipv6_dns(self, dns6):
        """Add an IPv6 nameserver to resolv.conf, keeping the existing ones.

        Args:
            dns6 (str): the IPv6 nameserver address to add. Nothing is
                written if resolv.conf already lists it.
        """
        resolv_path = '/etc/resolv.conf'
        with open(resolv_path, 'r', encoding='utf-8') as resolv_file:
            content = resolv_file.read()
        if f'nameserver {dns6}' not in content:
            with open(resolv_path, 'a', encoding='utf-8') as resolv_file:
                resolv_file.write(f'nameserver {dns6}\n')

    def remove_rc_conf_var(self, varname):
        """Remove a variable from rc.conf using sysrc.

        Args:
            varname (str): the rc.conf variable to unset.
        """
        run(['sysrc', '-x', varname], check=False)

    def hide_window(self):
        """Hide the window.

        Returns:
            bool: False, so GLib.idle_add does not call this again.
        """
        self.hide()
        return False

    def discard_pending_changes(self, _widget):
        """Close the window without applying anything.

        Args:
            _widget (Gtk.Widget): the Cancel button, unused.
        """
        self.destroy()

    def set_rc_conf(self, name, value):
        """Set one rc.conf variable through sysrc.

        sysrc writes the value between double quotes without escaping it,
        and rc.conf is run by the shell as root at boot, so a value holding
        a quote, $(...) or a backtick would run as root. The entries are
        checked by NetworkMgr.validate before they get here. As a last
        guard, a name outside RC_CONF_NAME_REGEX or a value with any
        character outside RC_CONF_SAFE_REGEX is refused rather than written.

        Args:
            name (str): the rc.conf variable, for instance ifconfig_em0.
            value (str): its value, for instance "inet 10.0.0.2 netmask
                255.255.255.0". Spaces are fine.

        Raises:
            ValueError: when the name or the value holds a character that
                is not safe in rc.conf.
        """
        if not RC_CONF_NAME_REGEX.fullmatch(name) \
                or not RC_CONF_SAFE_REGEX.fullmatch(value):
            raise ValueError(f'Refusing to write {name!r}={value!r} to rc.conf.')
        run(['sysrc', f'{name}={value}'], check=False)

    def _build_vpn_tab(self):
        """Build the VPN Settings tab listing OpenVPN and WireGuard profiles."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_border_width(12)

        # Columns: display_name, type_label, gateway, status,
        #          profile_id, vpn_type, config_path, needs_auth, username
        self.vpn_store = Gtk.ListStore(
            str, str, str, str, str, str, str, bool, str
        )
        self.vpn_tree = Gtk.TreeView(model=self.vpn_store)
        self.vpn_tree.set_headers_visible(True)

        columns = [
            ("Name", 0, 150),
            ("Type", 1, 90),
            ("Gateway", 2, 160),
            ("Status", 3, 100),
        ]
        for title, col_idx, min_width in columns:
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=col_idx)
            column.set_min_width(min_width)
            column.set_resizable(True)
            self.vpn_tree.append_column(column)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.vpn_tree)
        vbox.pack_start(scroll, True, True, 0)

        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vbox.pack_start(btn_bar, False, False, 0)

        import_btn = Gtk.Button(label="Import VPN...")
        import_btn.connect("clicked", self.on_import_vpn_clicked)
        btn_bar.pack_start(import_btn, False, False, 0)

        new_btn = Gtk.Button(label="New OpenVPN")
        new_btn.connect("clicked", self.on_new_vpn_clicked)
        btn_bar.pack_start(new_btn, False, False, 0)

        new_ipsec_btn = Gtk.Button(label="New IPsec / L2TP")
        new_ipsec_btn.connect("clicked", self.on_new_ipsec_clicked)
        btn_bar.pack_start(new_ipsec_btn, False, False, 0)

        edit_btn = Gtk.Button(label="Edit")
        edit_btn.connect("clicked", self.on_edit_vpn_clicked)
        btn_bar.pack_start(edit_btn, False, False, 0)

        toggle_btn = Gtk.Button(label="Connect / Disconnect")
        toggle_btn.connect("clicked", self.on_toggle_vpn_clicked)
        btn_bar.pack_start(toggle_btn, False, False, 0)

        delete_btn = Gtk.Button(label="Delete")
        delete_btn.connect("clicked", self.on_delete_vpn_clicked)
        btn_bar.pack_end(delete_btn, False, False, 0)

        self.refresh_vpn_list()
        return vbox

    def refresh_vpn_list(self):
        """Reload all OpenVPN, WireGuard, and IPsec/L2TP profiles into the VPN tab store."""
        if not hasattr(self, 'vpn_store'):
            return
        self.vpn_store.clear()

        ovpn_info = openvpn_dictionary()
        for pid, meta in ovpn_info.get('configs', {}).items():
            self.vpn_store.append([
                meta.get('info', pid),
                'OpenVPN',
                meta.get('gateway', ''),
                meta.get('state', 'Disconnected'),
                pid,
                'openvpn',
                meta.get('path', ''),
                bool(meta.get('needs_auth', False)),
                meta.get('username', ''),
            ])

        wg_info = wg_dictionary(wg_service_state())
        for pid, meta in wg_info.get('configs', {}).items():
            self.vpn_store.append([
                meta.get('info', pid),
                'WireGuard',
                meta.get('gateway', ''),
                meta.get('state', 'Disconnected'),
                pid,
                'wireguard',
                meta.get('path', ''),
                False,
                '',
            ])

        ipsec_info = ipsec_dictionary()
        for pid, meta in ipsec_info.get('configs', {}).items():
            proto = meta.get('protocol', 'l2tp-ipsec')
            type_label = 'L2TP / IPsec' if proto == 'l2tp-ipsec' else 'IPsec (IKEv2/v1)'
            self.vpn_store.append([
                meta.get('info', pid),
                type_label,
                meta.get('gateway', ''),
                meta.get('state', 'Disconnected'),
                pid,
                'ipsec',
                meta.get('path', ''),
                False,
                proto,
            ])

    def _selected_vpn_row(self):
        """Return the currently selected row from the VPN TreeView, or None."""
        selection = self.vpn_tree.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            return None
        return {
            'name': model[tree_iter][0],
            'type_label': model[tree_iter][1],
            'gateway': model[tree_iter][2],
            'state': model[tree_iter][3],
            'profile_id': model[tree_iter][4],
            'vpn_type': model[tree_iter][5],
            'path': model[tree_iter][6],
            'needs_auth': model[tree_iter][7],
            'username': model[tree_iter][8],
        }

    def on_import_vpn_clicked(self, _widget):
        """Import an OpenVPN (.ovpn/.conf), WireGuard (.conf), or IPsec (.ipsec/.sswan) file."""
        import_vpn_file_dialog(
            parent=self,
            on_saved=lambda _pid, _vtype: self.refresh_vpn_list(),
        )

    def on_new_vpn_clicked(self, _widget):
        """Open the VPN editor to create a new OpenVPN profile from scratch."""
        editor = VPNConnectionDialog(
            default_openvpn_config('New VPN'),
            parent=self,
            on_saved=lambda _pid, _vtype: self.refresh_vpn_list(),
        )
        editor.show_all()
        editor.refresh_dynamic_visibility()

    def on_new_ipsec_clicked(self, _widget):
        """Open the VPN editor to create a new IPsec / L2TP profile from scratch."""
        editor = VPNConnectionDialog(
            default_ipsec_config('New IPsec VPN'),
            parent=self,
            on_saved=lambda _pid, _vtype: self.refresh_vpn_list(),
        )
        editor.show_all()
        editor.refresh_dynamic_visibility()

    def on_edit_vpn_clicked(self, _widget):
        """Open the VPN editor for the selected VPN profile."""
        sel = self._selected_vpn_row()
        if not sel or not sel['path']:
            return
        try:
            if sel['vpn_type'] == 'wireguard':
                cfg = parse_wireguard_config(sel['path'])
            elif sel['vpn_type'] == 'ipsec':
                cfg = parse_ipsec_config(sel['path'])
            else:
                cfg = parse_openvpn_config(sel['path'])
        except ValueError as err:
            self.show_invalid_entry(str(err))
            return
        editor = VPNConnectionDialog(
            cfg,
            parent=self,
            on_saved=lambda _pid, _vtype: self.refresh_vpn_list(),
        )
        editor.show_all()
        editor.refresh_dynamic_visibility()

    def on_toggle_vpn_clicked(self, _widget):
        """Connect or disconnect the selected VPN profile."""
        sel = self._selected_vpn_row()
        if not sel:
            return
        pid = sel['profile_id']
        display_name = sel['name'] or pid
        if sel['vpn_type'] == 'wireguard':
            if sel['state'] == 'Connected':
                disable_wg(pid)
                self.refresh_vpn_list()
                show_connection_notification(display_name, False)
            elif not is_wireguard_installed():
                show_wireguard_not_installed_alert(self)
            else:
                ok, err_msg = enable_wg(pid)
                self.refresh_vpn_list()
                if not ok:
                    if err_msg == WIREGUARD_NOT_INSTALLED_MSG:
                        show_wireguard_not_installed_alert(self)
                    else:
                        self.show_invalid_entry(err_msg)
                else:
                    show_connection_notification(display_name, True)
        elif sel['vpn_type'] == 'ipsec':
            protocol = sel['username'] or 'l2tp-ipsec'
            if sel['state'] == 'Connected':
                disable_ipsec(pid)
                self.refresh_vpn_list()
                show_connection_notification(display_name, False)
            elif not is_ipsec_installed(protocol):
                show_ipsec_not_installed_alert(protocol, self)
            else:
                ok, err_msg = enable_ipsec(pid)
                self.refresh_vpn_list()
                if not ok:
                    self.show_invalid_entry(err_msg)
                else:
                    show_connection_notification(display_name, True)
        else:
            if sel['state'] == 'Connected':
                disable_openvpn(pid)
                self.refresh_vpn_list()
                show_connection_notification(display_name, False)
            elif not is_openvpn_installed():
                show_openvpn_not_installed_alert(self)
            elif sel['needs_auth']:
                dialog = OpenVPNAuthDialog(
                    pid,
                    display_name,
                    initial_user=sel['username'],
                    on_submit=lambda p, u, pw, dn=display_name: self._connect_openvpn_from_tab(
                        p, u, pw, dn
                    ),
                )
                dialog.set_transient_for(self)
                dialog.show_all()
            else:
                self._connect_openvpn_from_tab(pid, None, None, display_name)

    def _connect_openvpn_from_tab(self, pid, username, password, display_name=None):
        """Start OpenVPN from the configuration tab and report errors."""
        if not is_openvpn_installed():
            show_openvpn_not_installed_alert(self)
            return
        ok, err_msg = enable_openvpn(pid, username=username, password=password)
        self.refresh_vpn_list()
        if not ok:
            if err_msg == OPENVPN_NOT_INSTALLED_MSG:
                show_openvpn_not_installed_alert(self)
            else:
                self.show_invalid_entry(err_msg)
            return
        show_connection_notification(display_name or pid, True)

    def on_delete_vpn_clicked(self, _widget):
        """Delete the selected VPN profile."""
        sel = self._selected_vpn_row()
        if not sel:
            return
        pid = sel['profile_id']
        if sel['vpn_type'] == 'wireguard':
            delete_wireguard_config(pid)
        elif sel['vpn_type'] == 'ipsec':
            delete_ipsec_config(pid)
        else:
            delete_openvpn_config(pid)
        self.refresh_vpn_list()


class ChooseVPNTypeDialog(Gtk.Dialog):
    """NetworkManager-style 'Choose a Connection Type' dialog for creating/importing VPNs."""

    CONNECTION_TYPES = (
        (
            'openvpn',
            'OpenVPN',
            'Compatible with OpenVPN servers (.ovpn / TLS / Password / Static Key).',
        ),
        (
            'l2tp-ipsec',
            'Layer 2 Tunneling Protocol (L2TP / IPsec)',
            'Compatible with Windows Server VPN, MikroTik, Ubiquiti, FortiGate, and L2TP/IPsec gateways.',
        ),
        (
            'ikev2-eap',
            'IPsec / IKEv2 (StrongSwan — EAP / Windows Server IKEv2)',
            'Compatible with Windows Server Always On VPN and IKEv2 EAP-MSCHAPv2 gateways.',
        ),
        (
            'ikev2-psk',
            'IPsec / IKEv2 with Pre-Shared Key (PSK)',
            'Standard IKEv2 tunnel authenticated with a Pre-Shared Key.',
        ),
        (
            'ikev2-cert',
            'IPsec / IKEv2 with X.509 Certificates',
            'Standard IKEv2 tunnel authenticated with client and CA certificates.',
        ),
        (
            'ikev1-xauth',
            'Cisco Compatible VPN (IPsec / IKEv1 XAuth + PSK)',
            'Compatible with Cisco IPsec / IKEv1 XAuth gateways.',
        ),
        (
            'wireguard',
            'WireGuard',
            'Modern high-performance WireGuard VPN tunnel (wg-quick).',
        ),
        (
            'import',
            'Import a saved VPN configuration...',
            'Import an existing .ovpn, .conf, .ipsec, or .sswan configuration file.',
        ),
    )

    def __init__(self, parent=None):
        super().__init__(
            title="Choose a Connection Type",
            transient_for=parent,
            flags=0,
        )
        self.set_default_size(500, 240)
        self.set_border_width(12)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            "Create...", Gtk.ResponseType.ACCEPT,
        )

        content = self.get_content_area()
        content.set_spacing(10)

        intro = Gtk.Label(
            label="Select the type of VPN connection you wish to create or import:"
        )
        intro.set_halign(Gtk.Align.START)
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
        intro.set_attributes(attrs)
        content.pack_start(intro, False, False, 4)

        self.type_combo = Gtk.ComboBoxText()
        for type_id, title, _desc in self.CONNECTION_TYPES:
            self.type_combo.append(type_id, title)
        self.type_combo.set_active(0)
        self.type_combo.connect("changed", self._on_type_changed)
        content.pack_start(self.type_combo, False, False, 0)

        self.desc_label = Gtk.Label()
        self.desc_label.set_halign(Gtk.Align.START)
        self.desc_label.set_line_wrap(True)
        self.desc_label.set_max_width_chars(62)
        content.pack_start(self.desc_label, False, False, 6)
        self._on_type_changed(self.type_combo)
        self.show_all()

    def _on_type_changed(self, combo):
        active_id = combo.get_active_id()
        for type_id, _title, desc in self.CONNECTION_TYPES:
            if type_id == active_id:
                self.desc_label.set_text(desc)
                break

    def get_selected_type(self):
        """Return the chosen connection type identifier."""
        return self.type_combo.get_active_id() or 'openvpn'


class NetworkSettingsWindow(Gtk.Window):
    """NetworkManager (`nm-connection-editor`) style Settings window.

    Displays all Ethernet, Wi-Fi, and VPN connections grouped by category in a
    single unified window. Allows configuring IPv4/IPv6 (DHCP, Static IP, DNS,
    Search Domains, and Static Routes) on Ethernet/Wi-Fi interfaces, as well as
    creating, importing, editing, connecting/disconnecting, and deleting VPNs
    (OpenVPN, WireGuard, L2TP/IPsec, IKEv2/IKEv1).
    """

    def __init__(self, on_changed=None):
        super().__init__(title="Network Connections — Settings")
        self.set_default_size(720, 480)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)
        self.on_changed = on_changed

        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(main_vbox)

        # TreeStore columns:
        #   0: Name (str)
        #   1: Type / Protocol (str)
        #   2: Address / Gateway (str)
        #   3: Status / Method (str)
        #   4: Category ('header' | 'nic' | 'vpn')
        #   5: Identifier (nic name or vpn profile_id)
        #   6: Subtype ('ethernet' | 'wifi' | 'openvpn' | 'wireguard' | 'ipsec')
        #   7: Config Path (str)
        #   8: Needs Auth (bool)
        #   9: Extra (username or ipsec protocol)
        self.tree_store = Gtk.TreeStore(
            str, str, str, str, str, str, str, str, bool, str
        )
        self.tree_view = Gtk.TreeView(model=self.tree_store)
        self.tree_view.set_headers_visible(True)
        self.tree_view.connect("row-activated", self.on_row_activated)
        self.tree_view.get_selection().connect(
            "changed", self._on_selection_changed
        )

        cols = (
            ("Connection / Interface", 0, 210),
            ("Type", 1, 135),
            ("IP / Gateway", 2, 175),
            ("Status", 3, 120),
        )
        for title, col_idx, min_w in cols:
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=col_idx)
            column.set_min_width(min_w)
            column.set_resizable(True)
            self.tree_view.append_column(column)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.tree_view)
        main_vbox.pack_start(scroll, True, True, 0)

        # Bottom action toolbar modeled after nm-connection-editor
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        main_vbox.pack_start(action_bar, False, False, 0)

        self.add_vpn_btn = Gtk.Button(label="+ Add VPN...")
        self.add_vpn_btn.set_tooltip_text(
            "Create a new VPN connection (OpenVPN, L2TP/IPsec, IKEv2, WireGuard) or import a file"
        )
        self.add_vpn_btn.connect("clicked", self.on_add_vpn_clicked)
        action_bar.pack_start(self.add_vpn_btn, False, False, 0)

        self.import_btn = Gtk.Button(label="Import VPN...")
        self.import_btn.set_tooltip_text(
            "Import an OpenVPN (.ovpn/.conf), WireGuard (.conf), or IPsec (.ipsec/.sswan) file"
        )
        self.import_btn.connect("clicked", self.on_import_clicked)
        action_bar.pack_start(self.import_btn, False, False, 0)

        self.edit_btn = Gtk.Button(label="Configure / Edit")
        self.edit_btn.set_tooltip_text(
            "Configure IPv4, IPv6, DNS, Static Routes, or VPN settings for the selected item"
        )
        self.edit_btn.connect("clicked", self.on_edit_clicked)
        action_bar.pack_start(self.edit_btn, False, False, 0)

        self.toggle_btn = Gtk.Button(label="Connect / Disconnect")
        self.toggle_btn.connect("clicked", self.on_toggle_clicked)
        action_bar.pack_start(self.toggle_btn, False, False, 0)

        self.delete_btn = Gtk.Button(label="– Delete")
        self.delete_btn.set_tooltip_text("Delete the selected VPN connection")
        self.delete_btn.connect("clicked", self.on_delete_clicked)
        action_bar.pack_start(self.delete_btn, False, False, 0)

        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda _w: self.destroy())
        action_bar.pack_end(close_btn, False, False, 0)

        self.refresh_connections()

    def _notify_changed(self):
        self.refresh_connections()
        if self.on_changed is not None:
            self.on_changed()

    def refresh_connections(self):
        """Populate Ethernet, Wi-Fi, and VPN sections in the TreeStore."""
        self.tree_store.clear()

        card_info = network_dictionary()
        cards = card_info.get('cards', {})
        all_nics = nics_list() or list(cards.keys())

        eth_nics = [n for n in all_nics if 'wlan' not in n]
        wifi_nics = [n for n in all_nics if 'wlan' in n]

        if eth_nics:
            eth_root = self.tree_store.append(
                None,
                ['Ethernet', '', '', '', 'header', '', '', '', False, ''],
            )
            for nic in eth_nics:
                try:
                    cfg4 = get_interface_settings(nic)
                except OSError:
                    cfg4 = {}
                method = cfg4.get('Assignment Method', 'DHCP')
                ip_addr = cfg4.get('Interface IP', '') or '—'
                gw = cfg4.get('Default Gateway', '')
                addr_str = f'{ip_addr} (GW {gw})' if gw and ip_addr != '—' else ip_addr
                conn_state = (
                    cards.get(nic, {}).get('state', {}).get('connection', method)
                )
                status_str = f'{conn_state} ({method})' if conn_state != method else method
                self.tree_store.append(
                    eth_root,
                    [
                        nic,
                        'Ethernet (802.3)',
                        addr_str,
                        status_str,
                        'nic',
                        nic,
                        'ethernet',
                        '',
                        False,
                        '',
                    ],
                )

        if wifi_nics:
            wifi_root = self.tree_store.append(
                None,
                ['Wi-Fi', '', '', '', 'header', '', '', '', False, ''],
            )
            for nic in wifi_nics:
                try:
                    cfg4 = get_interface_settings(nic)
                except OSError:
                    cfg4 = {}
                method = cfg4.get('Assignment Method', 'DHCP')
                ip_addr = cfg4.get('Interface IP', '') or '—'
                st = cards.get(nic, {}).get('state', {})
                conn_state = st.get('connection', method)
                ssid = st.get('ssid', '')
                name_str = f'{nic} ({ssid})' if ssid else nic
                status_str = f'{conn_state} ({method})' if conn_state != method else method
                self.tree_store.append(
                    wifi_root,
                    [
                        name_str,
                        'Wi-Fi (802.11)',
                        ip_addr,
                        status_str,
                        'nic',
                        nic,
                        'wifi',
                        '',
                        False,
                        '',
                    ],
                )

        vpn_root = self.tree_store.append(
            None,
            ['VPN Connections', '', '', '', 'header', '', '', '', False, ''],
        )

        ovpn_info = openvpn_dictionary()
        for pid, meta in ovpn_info.get('configs', {}).items():
            self.tree_store.append(
                vpn_root,
                [
                    meta.get('info', pid),
                    'OpenVPN',
                    meta.get('gateway', ''),
                    meta.get('state', 'Disconnected'),
                    'vpn',
                    pid,
                    'openvpn',
                    meta.get('path', ''),
                    bool(meta.get('needs_auth', False)),
                    meta.get('username', ''),
                ],
            )

        wg_info = wg_dictionary(wg_service_state())
        for pid, meta in wg_info.get('configs', {}).items():
            self.tree_store.append(
                vpn_root,
                [
                    meta.get('info', pid),
                    'WireGuard',
                    meta.get('gateway', ''),
                    meta.get('state', 'Disconnected'),
                    'vpn',
                    pid,
                    'wireguard',
                    meta.get('path', ''),
                    False,
                    '',
                ],
            )

        ipsec_info = ipsec_dictionary()
        for pid, meta in ipsec_info.get('configs', {}).items():
            proto = meta.get('protocol', 'l2tp-ipsec')
            type_label = 'L2TP / IPsec' if proto == 'l2tp-ipsec' else 'IPsec (IKEv2/v1)'
            self.tree_store.append(
                vpn_root,
                [
                    meta.get('info', pid),
                    type_label,
                    meta.get('gateway', ''),
                    meta.get('state', 'Disconnected'),
                    'vpn',
                    pid,
                    'ipsec',
                    meta.get('path', ''),
                    False,
                    proto,
                ],
            )

        self.tree_view.expand_all()
        self._on_selection_changed(self.tree_view.get_selection())

    def _selected_item(self):
        sel = self.tree_view.get_selection()
        model, it = sel.get_selected()
        if it is None:
            return None
        cat = model[it][4]
        if cat == 'header':
            return None
        return {
            'name': model[it][0],
            'type_label': model[it][1],
            'gateway': model[it][2],
            'state': model[it][3],
            'category': cat,
            'id': model[it][5],
            'subtype': model[it][6],
            'path': model[it][7],
            'needs_auth': model[it][8],
            'extra': model[it][9],
        }

    def _on_selection_changed(self, _selection):
        item = self._selected_item()
        has_item = item is not None
        is_vpn = has_item and item['category'] == 'vpn'
        self.edit_btn.set_sensitive(has_item)
        self.toggle_btn.set_sensitive(has_item)
        self.delete_btn.set_sensitive(is_vpn)

    def on_row_activated(self, _tree_view, _path, _column):
        """Double-clicking a row opens its configuration editor."""
        self.on_edit_clicked(None)

    def on_add_vpn_clicked(self, _widget):
        """Open the NetworkManager-style 'Choose a Connection Type' dialog."""
        chooser = ChooseVPNTypeDialog(parent=self)
        resp = chooser.run()
        chosen = chooser.get_selected_type()
        chooser.destroy()
        if resp != Gtk.ResponseType.ACCEPT:
            return

        if chosen == 'import':
            import_vpn_file_dialog(
                parent=self,
                on_saved=lambda _pid, _vtype: self._notify_changed(),
            )
            return

        if chosen == 'openvpn':
            if not is_openvpn_installed():
                show_openvpn_not_installed_alert(self)
            cfg = default_openvpn_config('New OpenVPN')
        elif chosen == 'wireguard':
            if not is_wireguard_installed():
                show_wireguard_not_installed_alert(self)
            cfg = default_wireguard_config('wg0')
        else:
            if not is_ipsec_installed(chosen):
                show_ipsec_not_installed_alert(chosen, self)
            cfg = default_ipsec_config('New IPsec VPN')
            cfg['protocol'] = chosen

        editor = VPNConnectionDialog(
            cfg,
            parent=self,
            on_saved=lambda _pid, _vtype: self._notify_changed(),
        )
        editor.show_all()
        editor.refresh_dynamic_visibility()

    def on_import_clicked(self, _widget):
        """Import a VPN configuration file directly."""
        import_vpn_file_dialog(
            parent=self,
            on_saved=lambda _pid, _vtype: self._notify_changed(),
        )

    def on_edit_clicked(self, _widget):
        """Open the interface editor (Ethernet/Wi-Fi) or VPN editor for the selected row."""
        item = self._selected_item()
        if not item:
            return

        if item['category'] == 'nic':
            nic_win = NetCardConfigWindow(
                selected_nic=item['id'],
                on_saved=self._notify_changed,
            )
            nic_win.set_transient_for(self)
            nic_win.show_all()
            return

        if not item['path']:
            return
        try:
            if item['subtype'] == 'wireguard':
                cfg = parse_wireguard_config(item['path'])
            elif item['subtype'] == 'ipsec':
                cfg = parse_ipsec_config(item['path'])
            else:
                cfg = parse_openvpn_config(item['path'])
        except ValueError as err:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Could not open VPN configuration",
            )
            dialog.format_secondary_text(str(err))
            dialog.run()
            dialog.destroy()
            return

        editor = VPNConnectionDialog(
            cfg,
            parent=self,
            on_saved=lambda _pid, _vtype: self._notify_changed(),
        )
        editor.show_all()
        editor.refresh_dynamic_visibility()

    def on_toggle_clicked(self, _widget):
        """Connect or disconnect the selected Ethernet, Wi-Fi, or VPN item."""
        item = self._selected_item()
        if not item:
            return

        ident = item['id']
        display_name = item['name'] or ident
        is_connected = item['state'].startswith('Connected') or item['state'] == 'Connecting'

        if item['category'] == 'nic':
            if item['subtype'] == 'wifi':
                if is_connected:
                    disable_wifi(ident)
                    show_connection_notification(ident, False)
                else:
                    enable_wifi(ident)
                    show_connection_notification(ident, True)
            else:
                if is_connected:
                    stop_network_card(ident)
                    show_connection_notification(ident, False)
                else:
                    start_network_card(ident)
                    show_connection_notification(ident, True)
            self._notify_changed()
            return

        # VPN item
        if item['subtype'] == 'wireguard':
            if is_connected:
                disable_wg(ident)
                show_connection_notification(display_name, False)
                self._notify_changed()
            elif not is_wireguard_installed():
                show_wireguard_not_installed_alert(self)
            else:
                ok, err_msg = enable_wg(ident)
                self._notify_changed()
                if not ok:
                    if err_msg == WIREGUARD_NOT_INSTALLED_MSG:
                        show_wireguard_not_installed_alert(self)
                    else:
                        self._show_error(err_msg)
                else:
                    show_connection_notification(display_name, True)
        elif item['subtype'] == 'ipsec':
            protocol = item['extra'] or 'l2tp-ipsec'
            if is_connected:
                disable_ipsec(ident)
                show_connection_notification(display_name, False)
                self._notify_changed()
            elif not is_ipsec_installed(protocol):
                show_ipsec_not_installed_alert(protocol, self)
            else:
                ok, err_msg = enable_ipsec(ident)
                self._notify_changed()
                if not ok:
                    self._show_error(err_msg)
                else:
                    show_connection_notification(display_name, True)
        else:  # openvpn
            if is_connected:
                disable_openvpn(ident)
                show_connection_notification(display_name, False)
                self._notify_changed()
            elif not is_openvpn_installed():
                show_openvpn_not_installed_alert(self)
            elif item['needs_auth']:
                dialog = OpenVPNAuthDialog(
                    ident,
                    display_name,
                    initial_user=item['extra'],
                    on_submit=lambda p, u, pw, dn=display_name: self._connect_ovpn(
                        p, u, pw, dn
                    ),
                )
                dialog.set_transient_for(self)
                dialog.show_all()
            else:
                self._connect_ovpn(ident, None, None, display_name)

    def _connect_ovpn(self, pid, username, password, display_name):
        if not is_openvpn_installed():
            show_openvpn_not_installed_alert(self)
            return
        ok, err_msg = enable_openvpn(pid, username=username, password=password)
        self._notify_changed()
        if not ok:
            if err_msg == OPENVPN_NOT_INSTALLED_MSG:
                show_openvpn_not_installed_alert(self)
            else:
                self._show_error(err_msg)
            return
        show_connection_notification(display_name or pid, True)

    def _show_error(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Connection Error",
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def on_delete_clicked(self, _widget):
        """Delete the selected VPN profile."""
        item = self._selected_item()
        if not item or item['category'] != 'vpn':
            return
        pid = item['id']
        if item['subtype'] == 'wireguard':
            delete_wireguard_config(pid)
        elif item['subtype'] == 'ipsec':
            delete_ipsec_config(pid)
        else:
            delete_openvpn_config(pid)
        self._notify_changed()


def open_network_settings(on_changed=None):
    """Open the unified NetworkManager-style Network Connections / Settings window."""
    win = NetworkSettingsWindow(on_changed=on_changed)
    win.show_all()
    win.present()
    if Gtk.main_level() == 0:
        win.connect("destroy", Gtk.main_quit)
        Gtk.main()
    return win


def open_configuration(default_int):
    """Open the configuration window for one interface and run GTK.

    Args:
        default_int (str): the interface to select when the window opens.
    """
    win = NetCardConfigWindow(default_int)
    win.show_all()
    win.present()
    if Gtk.main_level() == 0:
        win.connect("destroy", Gtk.main_quit)
        Gtk.main()


def open_default_configuration():
    """Open the configuration window on the default interface and run GTK."""
    win = NetCardConfigWindow()
    win.show_all()
    win.present()
    if Gtk.main_level() == 0:
        win.connect("destroy", Gtk.main_quit)
        Gtk.main()
