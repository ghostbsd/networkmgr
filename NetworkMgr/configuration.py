#!/usr/bin/env python

"""The per-interface network configuration window.

Two tabs, IPv4 and IPv6, each offering an automatic mode (DHCP or SLAAC) or
a manual address, mask, gateway, DNS and search domain. Saving writes
rc.conf through sysrc and /etc/resolv.conf directly, then applies the same
settings to the running system through NetworkMgr.net_api.
"""

import re
from subprocess import DEVNULL, run

import gi
gi.require_version('Gtk', '3.0')

# gi.require_version() has to run before the typelib is loaded, so the
# imports below cannot be hoisted above it.
# pylint: disable=wrong-import-position
from gi.repository import Gtk, GLib
from NetworkMgr.net_api import (
    default_card,
    nics_list,
    restart_card_network,
    restart_routing_and_dhcp,
    start_static_network,
    start_static_ipv6_network,
    enable_slaac,
    disable_slaac,
    wait_for_address
)
from NetworkMgr.query import get_interface_settings, get_interface_settings_ipv6


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

    def __init__(self, selected_nic=None):
        # Build Default Window
        Gtk.Window.__init__(self, title="Network Configuration")
        self.set_default_size(475, 400)
        self.nics = nics_list()
        default_nic = selected_nic if selected_nic else default_card()
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
        # Put all the widgets together into one window
        main_box = Gtk.Box(orientation=1, spacing=0)
        main_box.pack_start(nb, True, True, 0)
        main_box.pack_end(buttons_window, False, False, 0)
        self.add(main_box)

    # Used with the combo box to refresh the UI of tab 1 with active settings
    # for the newly selected active interface.
    def cbox_config_refresh(self, widget):
        """Reload both tabs for the interface just chosen in the combo box.

        Args:
            widget (Gtk.ComboBox): the interface combo box.
        """
        selected_nic = self.nics[widget.get_active()]
        self.current_settings = get_interface_settings(selected_nic)
        self.current_settings6 = get_interface_settings_ipv6(selected_nic)
        self.update_interface_settings()
        self.update_interface_settings_ipv6()

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
        """Hide the window and apply the settings on the GTK idle handler.

        Args:
            _widget (Gtk.Widget): the Save button, unused.
        """
        self.hide_window()
        GLib.idle_add(self.update_system)

    def update_system(self):
        """Write the chosen IPv4 and IPv6 settings and apply them.

        rc.conf is updated through sysrc, /etc/resolv.conf is rewritten for
        a manual configuration, and the interface is restarted so the new
        settings take effect straight away.
        """
        nic = self.current_settings["Active Interface"]
        inet = self.ip_input_address_entry.get_text()
        netmask = self.ip_input_mask_entry.get_text()
        defaultrouter = self.ip_input_gateway_entry.get_text()
        if self.method == 'Manual':
            if 'wlan' in nic:
                ifconfig_value = f'WPA inet {inet} netmask {netmask}'
            else:
                ifconfig_value = f'inet {inet} netmask {netmask}'
            self.set_rc_conf(f'ifconfig_{nic}', ifconfig_value)
            self.set_rc_conf('defaultrouter', defaultrouter)
            start_static_network(nic, inet, netmask)
            with open('/etc/resolv.conf', 'w', encoding='utf-8') as resolv_conf:
                resolv_conf.writelines('# Generated by NetworkMgr\n')
                search = self.search_entry.get_text()
                if search:
                    search_line = f'search {search}\n'
                    resolv_conf.writelines(search_line)
                dns1 = self.prymary_dns_entry.get_text()
                nameserver1_line = f'nameserver {dns1}\n'
                resolv_conf.writelines(nameserver1_line)
                dns2 = self.secondary_dns_entry.get_text()
                if dns2:
                    nameserver2_line = f'nameserver {dns2}\n'
                    resolv_conf.writelines(nameserver2_line)
        else:
            self.set_rc_conf(f'ifconfig_{nic}',
                             'WPA DHCP' if 'wlan' in nic else 'DHCP')

            with open('/etc/rc.conf', 'r', encoding='utf-8') as rc_conf_file:
                rc_conf = rc_conf_file.read()
            for nic_search in self.nics:
                if re.search(f'^ifconfig_{nic_search}=".*inet', rc_conf, re.MULTILINE):
                    break
            else:
                # Nothing static left, so dhclient takes the default
                # route back.
                self.remove_rc_conf_var('defaultrouter')
            restart_card_network(nic)
            # sometimes the inet address isn't available immediately after dhcp is enabled.
            start_static_network(nic, inet, netmask)
            wait_for_address(nic)
            restart_routing_and_dhcp(nic)

        # Apply IPv6 configuration
        self.update_system_ipv6(nic)

        self.destroy()

    def update_system_ipv6(self, nic):
        """Apply IPv6 configuration changes."""
        inet6 = self.ip_input_address_entry6.get_text()
        prefixlen = self.ip_input_mask_entry6.get_text() or "64"
        gateway6 = self.ip_input_gateway_entry6.get_text()
        dns6 = self.prymary_dns_entry6.get_text()

        if self.method6 == 'Manual':
            # Static IPv6 configuration
            self.set_rc_conf(f'ifconfig_{nic}_ipv6',
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
            self.set_rc_conf(f'ifconfig_{nic}_ipv6', 'inet6 accept_rtadv')

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

        The name and the value are passed as a single argument rather than
        built into a shell command, so a value holding spaces needs no
        quoting and a value holding a quote or a semicolon cannot run
        anything. sysrc adds the quotes when it writes the file.

        Args:
            name (str): the rc.conf variable, for instance ifconfig_em0.
            value (str): its value, for instance "inet 10.0.0.2 netmask
                255.255.255.0". Spaces are fine.
        """
        run(['sysrc', f'{name}={value}'], check=False)


def open_configuration(default_int):
    """Open the configuration window for one interface and run GTK.

    Args:
        default_int (str): the interface to select when the window opens.
    """
    win = NetCardConfigWindow(default_int)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    win.set_keep_above(True)
    Gtk.main()


def open_default_configuration():
    """Open the configuration window on the default interface and run GTK."""
    win = NetCardConfigWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    win.set_keep_above(True)
    Gtk.main()
