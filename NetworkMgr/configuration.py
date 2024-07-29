#!/usr/bin/env python

import gi
import os
import re

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from NetworkMgr.net_api import (
    default_card,
    nics_list,
    restart_card_network,
    restart_routing_and_dhcp,
    start_static_network,
    wait_inet
)
from NetworkMgr.query import get_interface_settings
from subprocess import run

rcconf = open('/etc/rc.conf', 'r').read()
if os.path.exists('/etc/rc.conf.local'):
    rcconflocal = open('/etc/rc.conf.local', 'r').read()
else:
    rcconflocal = "None"


class NetCardConfigWindow(Gtk.Window):

    def edit_ipv4_setting(self, widget):
        if widget.get_active():
            self.method = widget.get_label()
            if self.method == "DHCP":
                self.ipInputAddressEntry.set_sensitive(False)
                self.ipInputMaskEntry.set_sensitive(False)
                self.ipInputGatewayEntry.set_sensitive(False)
                self.primary_dns_entry.set_sensitive(False)
                self.secondary_dns_entry.set_sensitive(False)
            else:
                self.ipInputAddressEntry.set_sensitive(True)
                self.ipInputMaskEntry.set_sensitive(True)
                self.ipInputGatewayEntry.set_sensitive(True)
                self.primary_dns_entry.set_sensitive(True)
                self.secondary_dns_entry.set_sensitive(True)
            if self.method == self.currentSettings["Assignment Method"]:
                self.saveButton.set_sensitive(False)
            else:
                self.saveButton.set_sensitive(True)

    def edit_ipv6_setting(self, widget, value):
        if value == "SLAAC":
            self.ip_input_address_entry6.set_sensitive(False)
            self.ip_input_mask_entry6.set_sensitive(False)
            self.ip_input_gateway_entry6.set_sensitive(False)
            self.primary_dns_entry6.set_sensitive(False)
            self.search_entry6.set_sensitive(False)
            self.saveButton.set_sensitive(False)
        else:
            self.ip_input_address_entry6.set_sensitive(True)
            self.ip_input_mask_entry6.set_sensitive(True)
            self.ip_input_gateway_entry6.set_sensitive(True)
            self.primary_dns_entry6.set_sensitive(True)
            self.search_entry6.set_sensitive(True)
            self.saveButton.set_sensitive(True)

    def entry_trigger_save_button(self, widget, event):
        self.saveButton.set_sensitive(True)

    def __init__(self, selected_nic=None):
        # Build Default Window
        Gtk.Window.__init__(self, title="Network Configuration")
        self.set_default_size(475, 400)
        self.NICS = nics_list()
        default_nic = selected_nic if selected_nic else default_card()
        # Build Tab 1 Content
        # Interface Drop Down Combo Box
        cell = Gtk.CellRendererText()

        interface_combo_box = Gtk.ComboBox()
        interface_combo_box.pack_start(cell, expand=True)
        interface_combo_box.add_attribute(cell, 'text', 0)

        # Add interfaces to a ListStore
        store = Gtk.ListStore(str)

        for nic in self.NICS:
            store.append([nic])

        interface_combo_box.set_model(store)
        interface_combo_box.set_margin_top(15)
        interface_combo_box.set_margin_end(30)
        if default_nic:
            active_index = self.NICS.index(f"{default_nic}")
            interface_combo_box.set_active(active_index)
        self.currentSettings = get_interface_settings(default_nic)
        self.method = self.currentSettings["Assignment Method"]
        interface_combo_box.connect("changed", self.cbox_config_refresh, self.NICS)

        # Build Label to sit in front of the ComboBox
        label_one = Gtk.Label(label="Interface:")
        label_one.set_margin_top(15)
        label_one.set_margin_start(30)

        # Add both objects to a single box, which will then be added to the grid
        interface_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=100)
        interface_box.pack_start(label_one, False, False, 0)
        interface_box.pack_end(interface_combo_box, True, True, 0)

        # Add radio button to toggle DHCP or not
        self.version = self.currentSettings["Assignment Method"]
        self.rb_dhcp4 = Gtk.RadioButton.new_with_label(None, "DHCP")
        self.rb_dhcp4.set_margin_top(15)
        self.rb_manual4 = Gtk.RadioButton.new_with_label_from_widget(
            self.rb_dhcp4, "Manual")
        self.rb_manual4.set_margin_top(15)
        if self.currentSettings["Assignment Method"] == "DHCP":
            self.rb_dhcp4.set_active(True)
        else:
            self.rb_manual4.set_active(True)
        self.rb_manual4.join_group(self.rb_dhcp4)

        radio_button_label = Gtk.Label(label="IPv4 Method:")
        radio_button_label.set_margin_top(15)
        radio_button_label.set_margin_start(30)

        radio_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
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

        self.ipInputAddressEntry = Gtk.Entry()
        self.ipInputAddressEntry.set_margin_start(15)
        self.ipInputAddressEntry.set_text(self.currentSettings["Interface IP"])
        self.ipInputAddressEntry.connect("key-release-event", self.entry_trigger_save_button)

        self.ipInputMaskEntry = Gtk.Entry()
        self.ipInputMaskEntry.set_text(self.currentSettings["Interface Subnet Mask"])
        self.ipInputMaskEntry.connect("key-release-event", self.entry_trigger_save_button)

        self.ipInputGatewayEntry = Gtk.Entry()
        self.ipInputGatewayEntry.set_margin_end(15)
        self.ipInputGatewayEntry.set_text(self.currentSettings["Default Gateway"])
        self.ipInputGatewayEntry.connect("key-release-event", self.entry_trigger_save_button)

        ip_input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        ip_input_box.set_homogeneous(True)
        ip_input_box.pack_start(ip_input_address_label, False, False, 0)
        ip_input_box.pack_start(ip_input_mask_label, False, False, 0)
        ip_input_box.pack_start(ip_input_gateway_label, False, False, 0)

        ip_entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=30)
        ip_entry_box.pack_start(self.ipInputAddressEntry, False, False, 0)
        ip_entry_box.pack_start(self.ipInputMaskEntry, False, False, 0)
        ip_entry_box.pack_start(self.ipInputGatewayEntry, False, False, 0)

        # Add DNS Server Settings
        primary_dns_label = Gtk.Label(label="Primary DNS Servers: ")
        primary_dns_label.set_margin_top(15)
        primary_dns_label.set_margin_end(58)
        primary_dns_label.set_margin_start(30)

        secondary_dns_label = Gtk.Label(label="Secondary DNS Servers: ")
        secondary_dns_label.set_margin_top(15)
        secondary_dns_label.set_margin_end(58)
        secondary_dns_label.set_margin_start(30)

        self.primary_dns_entry = Gtk.Entry()
        self.primary_dns_entry.set_margin_end(30)
        self.primary_dns_entry.set_text(self.currentSettings["DNS Server 1"])
        self.primary_dns_entry.connect("key-release-event", self.entry_trigger_save_button)

        self.secondary_dns_entry = Gtk.Entry()
        self.secondary_dns_entry.set_margin_end(30)
        self.secondary_dns_entry.set_text(self.currentSettings["DNS Server 2"])
        self.secondary_dns_entry.connect("key-release-event", self.entry_trigger_save_button)

        dns_entry_box1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        dns_entry_box1.pack_start(primary_dns_label, False, False, 0)

        dns_entry_box1.pack_end(self.primary_dns_entry, True, True, 0)

        dns_entry_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        dns_entry_box2.pack_start(secondary_dns_label, False, False, 0)

        dns_entry_box2.pack_end(self.secondary_dns_entry, True, True, 0)

        # Add Search Domain Settings
        search_label = Gtk.Label(label="Search domains: ")
        search_label.set_margin_top(15)
        search_label.set_margin_end(30)
        search_label.set_margin_start(30)

        self.searchEntry = Gtk.Entry()
        self.searchEntry.set_margin_top(21)
        self.searchEntry.set_margin_end(30)
        self.searchEntry.set_margin_bottom(30)
        self.searchEntry.set_text(self.currentSettings["Search Domain"])
        self.searchEntry.connect("key-release-event", self.entry_trigger_save_button)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        search_box.pack_start(search_label, False, False, 0)
        search_box.pack_end(self.searchEntry, True, True, 0)

        self.rb_dhcp4.connect("toggled", self.edit_ipv4_setting)
        self.rb_manual4.connect("toggled", self.edit_ipv4_setting)

        if self.currentSettings["Assignment Method"] == "DHCP":
            self.ipInputAddressEntry.set_sensitive(False)
            self.ipInputMaskEntry.set_sensitive(False)
            self.ipInputGatewayEntry.set_sensitive(False)
            self.primary_dns_entry.set_sensitive(False)
            self.secondary_dns_entry.set_sensitive(False)
            self.searchEntry.set_sensitive(False)

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
        for validinterface6 in self.NICS:
            store6.append([validinterface6])

        interface_combo_box6.set_model(store)
        interface_combo_box6.set_margin_top(15)
        interface_combo_box6.set_margin_end(30)

        if default_nic:
            active_combo_box_object_index6 = self.NICS.index(f"{default_nic}")
            interface_combo_box6.set_active(active_combo_box_object_index6)
        interface_combo_box6.connect("changed", self.cbox_config_refresh)

        # Build Label to sit in front of the ComboBox
        label_one6 = Gtk.Label(label="Interface:")
        label_one6.set_margin_top(15)
        label_one6.set_margin_start(30)

        # Add both objects to a single box, which will then be added to the grid
        interface_box6 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=100)
        interface_box6.pack_start(label_one6, False, False, 0)
        interface_box6.pack_end(interface_combo_box6, True, True, 0)

        # Add radio button to toggle DHCP or not
        rb_slaac6 = Gtk.RadioButton.new_with_label(None, "SLAAC")
        rb_slaac6.set_margin_top(15)
        rb_slaac6.connect("toggled", self.edit_ipv6_setting, "SLAAC")
        rb_manual6 = Gtk.RadioButton.new_with_label_from_widget(
            rb_slaac6, "Manual")
        rb_manual6.set_margin_top(15)
        rb_manual6.join_group(rb_slaac6)
        rb_manual6.connect("toggled", self.edit_ipv6_setting, "Manual")

        radio_button_label6 = Gtk.Label(label="IPv4 Method:")
        radio_button_label6.set_margin_top(15)
        radio_button_label6.set_margin_start(30)

        radio_box6 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
        radio_box6.set_homogeneous(False)
        radio_box6.pack_start(radio_button_label6, False, False, 0)
        radio_box6.pack_start(rb_slaac6, True, False, 0)
        radio_box6.pack_end(rb_manual6, True, True, 0)

        # Add Manual Address Field
        ip_input_address_label6 = Gtk.Label(label="Address")
        ip_input_address_label6.set_margin_top(15)

        ip_input_mask_label6 = Gtk.Label(label="Subnet Mask")
        ip_input_mask_label6.set_margin_top(15)

        ip_input_gateway_label6 = Gtk.Label(label="Gateway")
        ip_input_gateway_label6.set_margin_top(15)

        self.ip_input_address_entry6 = Gtk.Entry()
        self.ip_input_address_entry6.set_margin_start(15)
        self.ip_input_address_entry6.connect("key-release-event", self.entry_trigger_save_button)
        self.ip_input_mask_entry6 = Gtk.Entry()
        self.ip_input_address_entry6.connect("key-release-event", self.entry_trigger_save_button)
        self.ip_input_gateway_entry6 = Gtk.Entry()
        self.ip_input_gateway_entry6.set_margin_end(15)
        self.ip_input_gateway_entry6.connect("key-release-event", self.entry_trigger_save_button)

        ip_input_box6 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        ip_input_box6.set_homogeneous(True)
        ip_input_box6.pack_start(ip_input_address_label6, False, False, 0)
        ip_input_box6.pack_start(ip_input_mask_label6, False, False, 0)
        ip_input_box6.pack_start(ip_input_gateway_label6, False, False, 0)

        ip_entry_box6 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=30)
        ip_entry_box6.pack_start(self.ip_input_address_entry6, False, False, 0)
        ip_entry_box6.pack_start(self.ip_input_mask_entry6, False, False, 0)
        ip_entry_box6.pack_start(self.ip_input_gateway_entry6, False, False, 0)

        # Add DNS Server Settings
        primary_dns_label6 = Gtk.Label(label="Primary DNS Servers: ")
        primary_dns_label6.set_margin_top(15)
        primary_dns_label6.set_margin_end(58)
        primary_dns_label6.set_margin_start(30)

        secondary_dns_label6 = Gtk.Label(label="Secondary DNS Servers: ")
        secondary_dns_label6.set_margin_top(15)
        secondary_dns_label6.set_margin_end(58)
        secondary_dns_label6.set_margin_start(30)

        self.primary_dns_entry6 = Gtk.Entry()
        self.primary_dns_entry6.set_margin_end(30)
        self.primary_dns_entry6.connect("key-release-event", self.entry_trigger_save_button)

        dns_entry_box6 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        dns_entry_box6.pack_start(primary_dns_label6, False, False, 0)
        dns_entry_box6.pack_end(self.primary_dns_entry6, True, True, 0)

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

        search_box6 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        search_box6.pack_start(search_label6, False, False, 0)
        search_box6.pack_end(self.search_entry6, True, True, 0)

        self.ip_input_address_entry6.set_sensitive(False)
        self.ip_input_mask_entry6.set_sensitive(False)
        self.ip_input_gateway_entry6.set_sensitive(False)
        self.primary_dns_entry6.set_sensitive(False)
        self.search_entry6.set_sensitive(False)

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
        grid_one6.set_sensitive(False)

        # Build Notebook

        nb = Gtk.Notebook()
        nb.set_margin_start(10)
        nb.set_margin_end(10)
        nb.set_margin_top(10)
        nb.set_margin_bottom(10)
        nb.set_tab_pos(2)
        # nb.set_sensitive(False)
        # Build Save & Cancel Buttons

        self.saveButton = Gtk.Button(label="Save")
        self.saveButton.set_margin_bottom(10)
        self.saveButton.set_margin_start(10)
        self.saveButton.connect("clicked", self.commit_pending_changes)
        self.saveButton.set_sensitive(False)
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.set_margin_bottom(10)
        cancel_button.connect("clicked", self.discard_pending_changes)
        buttons_window = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        buttons_window.pack_start(self.saveButton, False, False, 0)
        buttons_window.pack_start(cancel_button, False, False, 0)

        # Apply Tab 1 content and formatting to the notebook
        nb.append_page(grid_one)
        nb.set_tab_label_text(grid_one, "IPv4 Settings")

        # Apply Tab 2 content and formatting to the notebook
        nb.append_page(grid_one6)
        nb.set_tab_label_text(grid_one6, "IPv6 Settings WIP")
        # Put all the widgets together into one window
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_box.pack_start(nb, True, True, 0)
        main_box.pack_end(buttons_window, False, False, 0)
        self.add(main_box)

    # Used with the combo box to refresh the UI of tab 1 with active settings
    # for the newly selected active interface.
    def cbox_config_refresh(self, widget, nics):
        # actions here need to refresh the values on the first two tabs.
        self.currentSettings = get_interface_settings(nics[widget.get_active()])
        self.update_interface_settings()

    def update_interface_settings(self):
        self.ipInputAddressEntry.set_text(self.currentSettings["Interface IP"])
        self.ipInputMaskEntry.set_text(self.currentSettings["Interface Subnet Mask"])
        self.ipInputGatewayEntry.set_text(self.currentSettings["Default Gateway"])
        self.primary_dns_entry.set_text(self.currentSettings["DNS Server 1"])
        self.secondary_dns_entry.set_text(self.currentSettings["DNS Server 2"])
        self.searchEntry.set_text(self.currentSettings["Search Domain"])
        if self.currentSettings["Assignment Method"] == "DHCP":
            self.rb_dhcp4.set_active(True)
        else:
            self.rb_manual4.set_active(True)

    def commit_pending_changes(self, widget):
        self.hide_window()
        GLib.idle_add(self.update_system)

    def update_system(self):
        nic = self.currentSettings["Active Interface"]
        inet = self.ipInputAddressEntry.get_text()
        netmask = self.ipInputMaskEntry.get_text()
        default_router = self.ipInputGatewayEntry.get_text()
        if self.method == 'Manual':
            if 'wlan' in nic:
                ifconfig_nic = f'ifconfig_{nic}="WPA inet {inet} netmask {netmask}"\n'
            else:
                ifconfig_nic = f'ifconfig_{nic}="inet {inet} netmask {netmask}"\n'
            self.update_rc_conf(ifconfig_nic)
            default_router_line = f'default_router="{default_router}"\n'
            self.update_rc_conf(default_router_line)
            start_static_network(nic, inet, netmask)
            resolv_conf = open('/etc/resolv.conf', 'w')
            resolv_conf.writelines('# Generated by NetworkMgr\n')
            search = self.searchEntry.get_text()
            if search:
                search_line = f'search {search}\n'
                resolv_conf.writelines(search_line)
            dns1 = self.primary_dns_entry.get_text()
            nameserver1_line = f'nameserver {dns1}\n'
            resolv_conf.writelines(nameserver1_line)
            dns2 = self.secondary_dns_entry.get_text()
            if dns2:
                nameserver2_line = f'nameserver {dns2}\n'
                resolv_conf.writelines(nameserver2_line)
            resolv_conf.close()
        else:
            if 'wlan' in nic:
                ifconfig_nic = f'ifconfig_{nic}="WPA DHCP"\n'
            else:
                ifconfig_nic = f'ifconfig_{nic}="DHCP"\n'
            self.update_rc_conf(ifconfig_nic)

            rc_conf = open('/etc/rc.conf', 'r').read()
            for nic_search in self.NICS:
                if re.search(f'^ifconfig_{nic_search}=".*inet', rc_conf, re.MULTILINE):
                    break
            else:
                default_router_line = f'default_router="{default_router}"\n'
                self.remove_rc_conf_line(default_router_line)
            restart_card_network(nic)
            # sometimes the inet address isn't available immediately after dhcp is enabled.
            start_static_network(nic, inet, netmask)
            wait_inet(nic)
            restart_routing_and_dhcp(nic)

        self.destroy()

    def hide_window(self):
        self.hide()
        return False

    def discard_pending_changes(self, widget):
        self.destroy()

    def update_rc_conf(self, line):
        run(f'sysrc {line}', shell=True)

    def remove_rc_conf_line(self, line):
        with open('/etc/rc.conf', "r+") as rc_conf:
            lines = rc_conf.readlines()
            rc_conf.seek(0)
            idx = lines.index(line)
            lines.pop(idx)
            rc_conf.truncate()
            rc_conf.writelines(lines)


def network_card_configuration(default_int):
    win = NetCardConfigWindow(default_int)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    win.set_keep_above(True)
    Gtk.main()


def network_card_configuration_window():
    win = NetCardConfigWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    win.set_keep_above(True)
    Gtk.main()
