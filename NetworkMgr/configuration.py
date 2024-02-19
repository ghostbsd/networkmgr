#!/usr/bin/env python

import gi
import os
import re
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from NetworkMgr.net_api import (
    defaultcard,
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


class netCardConfigWindow(Gtk.Window):

    def edit_ipv4_setting(self, widget):
        if widget.get_active():
            self.method = widget.get_label()
            if self.method == "DHCP":
                self.ipInputAddressEntry.set_sensitive(False)
                self.ipInputMaskEntry.set_sensitive(False)
                self.ipInputGatewayEntry.set_sensitive(False)
                self.prymary_dnsEntry.set_sensitive(False)
                self.secondary_dnsEntry.set_sensitive(False)
            else:
                self.ipInputAddressEntry.set_sensitive(True)
                self.ipInputMaskEntry.set_sensitive(True)
                self.ipInputGatewayEntry.set_sensitive(True)
                self.prymary_dnsEntry.set_sensitive(True)
                self.secondary_dnsEntry.set_sensitive(True)
            if self.method == self.currentSettings["Assignment Method"]:
                self.saveButton.set_sensitive(False)
            else:
                self.saveButton.set_sensitive(True)

    def edit_ipv6_setting(self, widget, value):
        if value == "SLAAC":
            self.ipInputAddressEntry6.set_sensitive(False)
            self.ipInputMaskEntry6.set_sensitive(False)
            self.ipInputGatewayEntry6.set_sensitive(False)
            self.prymary_dnsEntry6.set_sensitive(False)
            self.searchEntry6.set_sensitive(False)
            self.saveButton.set_sensitive(False)
        else:
            self.ipInputAddressEntry6.set_sensitive(True)
            self.ipInputMaskEntry6.set_sensitive(True)
            self.ipInputGatewayEntry6.set_sensitive(True)
            self.prymary_dnsEntry6.set_sensitive(True)
            self.searchEntry6.set_sensitive(True)
            self.saveButton.set_sensitive(True)

    def entry_trigger_save_button(self, widget, event):
        self.saveButton.set_sensitive(True)

    def __init__(self, selected_nic=None):
        # Build Default Window
        Gtk.Window.__init__(self, title="Network Configuration")
        self.set_default_size(475, 400)
        self.NICS = nics_list()
        DEFAULT_NIC = selected_nic if selected_nic else defaultcard()
        # Build Tab 1 Content
        # Interface Drop Down Combo Box
        cell = Gtk.CellRendererText()

        interfaceComboBox = Gtk.ComboBox()
        interfaceComboBox.pack_start(cell, expand=True)
        interfaceComboBox.add_attribute(cell, 'text', 0)

        # Add interfaces to a ListStore
        store = Gtk.ListStore(str)

        for nic in self.NICS:
            store.append([nic])

        interfaceComboBox.set_model(store)
        interfaceComboBox.set_margin_top(15)
        interfaceComboBox.set_margin_end(30)
        if DEFAULT_NIC:
            active_index = self.NICS.index(f"{DEFAULT_NIC}")
            interfaceComboBox.set_active(active_index)
        self.currentSettings = get_interface_settings(DEFAULT_NIC)
        self.method = self.currentSettings["Assignment Method"]
        interfaceComboBox.connect("changed", self.cbox_config_refresh, self.NICS)

        # Build Label to sit in front of the ComboBox
        labelOne = Gtk.Label(label="Interface:")
        labelOne.set_margin_top(15)
        labelOne.set_margin_start(30)

        # Add both objects to a single box, which will then be added to the grid
        interfaceBox = Gtk.Box(orientation=0, spacing=100)
        interfaceBox.pack_start(labelOne, False, False, 0)
        interfaceBox.pack_end(interfaceComboBox, True, True, 0)

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

        radioButtonLabel = Gtk.Label(label="IPv4 Method:")
        radioButtonLabel.set_margin_top(15)
        radioButtonLabel.set_margin_start(30)

        radioBox = Gtk.Box(orientation=0, spacing=50)
        radioBox.set_homogeneous(False)
        radioBox.pack_start(radioButtonLabel, False, False, 0)
        radioBox.pack_start(self.rb_dhcp4, True, False, 0)
        radioBox.pack_end(self.rb_manual4, True, True, 0)

        # Add Manual Address Field
        ipInputAddressLabel = Gtk.Label(label="Address")
        ipInputAddressLabel.set_margin_top(15)

        ipInputMaskLabel = Gtk.Label(label="Subnet Mask")
        ipInputMaskLabel.set_margin_top(15)

        ipInputGatewayLabel = Gtk.Label(label="Gateway")
        ipInputGatewayLabel.set_margin_top(15)

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

        ipInputBox = Gtk.Box(orientation=0, spacing=0)
        ipInputBox.set_homogeneous(True)
        ipInputBox.pack_start(ipInputAddressLabel, False, False, 0)
        ipInputBox.pack_start(ipInputMaskLabel, False, False, 0)
        ipInputBox.pack_start(ipInputGatewayLabel, False, False, 0)

        ipEntryBox = Gtk.Box(orientation=0, spacing=30)
        ipEntryBox.pack_start(self.ipInputAddressEntry, False, False, 0)
        ipEntryBox.pack_start(self.ipInputMaskEntry, False, False, 0)
        ipEntryBox.pack_start(self.ipInputGatewayEntry, False, False, 0)

        # Add DNS Server Settings
        prymary_dns_Label = Gtk.Label(label="Primary DNS Servers: ")
        prymary_dns_Label.set_margin_top(15)
        prymary_dns_Label.set_margin_end(58)
        prymary_dns_Label.set_margin_start(30)

        secondary_dns_Label = Gtk.Label(label="Secondary DNS Servers: ")
        secondary_dns_Label.set_margin_top(15)
        secondary_dns_Label.set_margin_end(58)
        secondary_dns_Label.set_margin_start(30)

        self.prymary_dnsEntry = Gtk.Entry()
        self.prymary_dnsEntry.set_margin_end(30)
        self.prymary_dnsEntry.set_text(self.currentSettings["DNS Server 1"])
        self.prymary_dnsEntry.connect("key-release-event", self.entry_trigger_save_button)

        self.secondary_dnsEntry = Gtk.Entry()
        self.secondary_dnsEntry.set_margin_end(30)
        self.secondary_dnsEntry.set_text(self.currentSettings["DNS Server 2"])
        self.secondary_dnsEntry.connect("key-release-event", self.entry_trigger_save_button)

        dnsEntryBox1 = Gtk.Box(orientation=0, spacing=0)
        dnsEntryBox1.pack_start(prymary_dns_Label, False, False, 0)

        dnsEntryBox1.pack_end(self.prymary_dnsEntry, True, True, 0)

        dnsEntryBox2 = Gtk.Box(orientation=0, spacing=0)
        dnsEntryBox2.pack_start(secondary_dns_Label, False, False, 0)

        dnsEntryBox2.pack_end(self.secondary_dnsEntry, True, True, 0)

        # Add Search Domain Settings
        searchLabel = Gtk.Label(label="Search domains: ")
        searchLabel.set_margin_top(15)
        searchLabel.set_margin_end(30)
        searchLabel.set_margin_start(30)

        self.searchEntry = Gtk.Entry()
        self.searchEntry.set_margin_top(21)
        self.searchEntry.set_margin_end(30)
        self.searchEntry.set_margin_bottom(30)
        self.searchEntry.set_text(self.currentSettings["Search Domain"])
        self.searchEntry.connect("key-release-event", self.entry_trigger_save_button)

        searchBox = Gtk.Box(orientation=0, spacing=0)
        searchBox.pack_start(searchLabel, False, False, 0)
        searchBox.pack_end(self.searchEntry, True, True, 0)

        self.rb_dhcp4.connect("toggled", self.edit_ipv4_setting)
        self.rb_manual4.connect("toggled", self.edit_ipv4_setting)

        if self.currentSettings["Assignment Method"] == "DHCP":
            self.ipInputAddressEntry.set_sensitive(False)
            self.ipInputMaskEntry.set_sensitive(False)
            self.ipInputGatewayEntry.set_sensitive(False)
            self.prymary_dnsEntry.set_sensitive(False)
            self.secondary_dnsEntry.set_sensitive(False)
            self.searchEntry.set_sensitive(False)

        gridOne = Gtk.Grid()
        gridOne.set_column_homogeneous(True)
        gridOne.set_row_homogeneous(False)
        gridOne.set_column_spacing(5)
        gridOne.set_row_spacing(10)
        gridOne.attach(interfaceBox, 0, 0, 4, 1)
        gridOne.attach(radioBox, 0, 1, 4, 1)
        gridOne.attach(ipInputBox, 0, 2, 4, 1)
        gridOne.attach(ipEntryBox, 0, 3, 4, 1)
        gridOne.attach(dnsEntryBox1, 0, 4, 4, 1)
        gridOne.attach(dnsEntryBox2, 0, 5, 4, 1)
        gridOne.attach(searchBox, 0, 6, 4, 1)

        # Build Tab 2 Content

        # Interface Drop Down Combo Box
        cell6 = Gtk.CellRendererText()

        interfaceComboBox6 = Gtk.ComboBox()
        interfaceComboBox6.pack_start(cell6, expand=True)
        interfaceComboBox6.add_attribute(cell6, 'text', 0)

        # Add interfaces to a ListStore
        store6 = Gtk.ListStore(str)
        for validinterface6 in self.NICS:
            store6.append([validinterface6])

        interfaceComboBox6.set_model(store)
        interfaceComboBox6.set_margin_top(15)
        interfaceComboBox6.set_margin_end(30)

        if DEFAULT_NIC:
            activeComboBoxObjectIndex6 = self.NICS.index(f"{DEFAULT_NIC}")
            interfaceComboBox6.set_active(activeComboBoxObjectIndex6)
        interfaceComboBox6.connect("changed", self.cbox_config_refresh)

        # Build Label to sit in front of the ComboBox
        labelOne6 = Gtk.Label(label="Interface:")
        labelOne6.set_margin_top(15)
        labelOne6.set_margin_start(30)

        # Add both objects to a single box, which will then be added to the grid
        interfaceBox6 = Gtk.Box(orientation=0, spacing=100)
        interfaceBox6.pack_start(labelOne6, False, False, 0)
        interfaceBox6.pack_end(interfaceComboBox6, True, True, 0)

        # Add radio button to toggle DHCP or not
        rb_slaac6 = Gtk.RadioButton.new_with_label(None, "SLAAC")
        rb_slaac6.set_margin_top(15)
        rb_slaac6.connect("toggled", self.edit_ipv6_setting, "SLAAC")
        rb_manual6 = Gtk.RadioButton.new_with_label_from_widget(
            rb_slaac6, "Manual")
        rb_manual6.set_margin_top(15)
        rb_manual6.join_group(rb_slaac6)
        rb_manual6.connect("toggled", self.edit_ipv6_setting, "Manual")

        radioButtonLabel6 = Gtk.Label(label="IPv4 Method:")
        radioButtonLabel6.set_margin_top(15)
        radioButtonLabel6.set_margin_start(30)

        radioBox6 = Gtk.Box(orientation=0, spacing=50)
        radioBox6.set_homogeneous(False)
        radioBox6.pack_start(radioButtonLabel6, False, False, 0)
        radioBox6.pack_start(rb_slaac6, True, False, 0)
        radioBox6.pack_end(rb_manual6, True, True, 0)

        # Add Manual Address Field
        ipInputAddressLabel6 = Gtk.Label(label="Address")
        ipInputAddressLabel6.set_margin_top(15)

        ipInputMaskLabel6 = Gtk.Label(label="Subnet Mask")
        ipInputMaskLabel6.set_margin_top(15)

        ipInputGatewayLabel6 = Gtk.Label(label="Gateway")
        ipInputGatewayLabel6.set_margin_top(15)

        self.ipInputAddressEntry6 = Gtk.Entry()
        self.ipInputAddressEntry6.set_margin_start(15)
        self.ipInputAddressEntry6.connect("key-release-event", self.entry_trigger_save_button)
        self.ipInputMaskEntry6 = Gtk.Entry()
        self.ipInputAddressEntry6.connect("key-release-event", self.entry_trigger_save_button)
        self.ipInputGatewayEntry6 = Gtk.Entry()
        self.ipInputGatewayEntry6.set_margin_end(15)
        self.ipInputGatewayEntry6.connect("key-release-event", self.entry_trigger_save_button)

        ipInputBox6 = Gtk.Box(orientation=0, spacing=0)
        ipInputBox6.set_homogeneous(True)
        ipInputBox6.pack_start(ipInputAddressLabel6, False, False, 0)
        ipInputBox6.pack_start(ipInputMaskLabel6, False, False, 0)
        ipInputBox6.pack_start(ipInputGatewayLabel6, False, False, 0)

        ipEntryBox6 = Gtk.Box(orientation=0, spacing=30)
        ipEntryBox6.pack_start(self.ipInputAddressEntry6, False, False, 0)
        ipEntryBox6.pack_start(self.ipInputMaskEntry6, False, False, 0)
        ipEntryBox6.pack_start(self.ipInputGatewayEntry6, False, False, 0)

        # Add DNS Server Settings
        prymary_dns_Label6 = Gtk.Label(label="Primary DNS Servers: ")
        prymary_dns_Label6.set_margin_top(15)
        prymary_dns_Label6.set_margin_end(58)
        prymary_dns_Label6.set_margin_start(30)

        secondary_dns_Label6 = Gtk.Label(label="Secondary DNS Servers: ")
        secondary_dns_Label6.set_margin_top(15)
        secondary_dns_Label6.set_margin_end(58)
        secondary_dns_Label6.set_margin_start(30)

        self.prymary_dnsEntry6 = Gtk.Entry()
        self.prymary_dnsEntry6.set_margin_end(30)
        self.prymary_dnsEntry6.connect("key-release-event", self.entry_trigger_save_button)

        dnsEntryBox6 = Gtk.Box(orientation=0, spacing=0)
        dnsEntryBox6.pack_start(prymary_dns_Label6, False, False, 0)
        dnsEntryBox6.pack_end(self.prymary_dnsEntry6, True, True, 0)

        # Add Search Domain Settings

        searchLabel6 = Gtk.Label(label="Search domains: ")
        searchLabel6.set_margin_top(15)
        searchLabel6.set_margin_end(30)
        searchLabel6.set_margin_start(30)

        self.searchEntry6 = Gtk.Entry()
        self.searchEntry6.set_margin_top(21)
        self.searchEntry6.set_margin_end(30)
        self.searchEntry6.set_margin_bottom(30)
        self.searchEntry6.connect("key-release-event", self.entry_trigger_save_button)

        searchBox6 = Gtk.Box(orientation=0, spacing=0)
        searchBox6.pack_start(searchLabel6, False, False, 0)
        searchBox6.pack_end(self.searchEntry6, True, True, 0)

        self.ipInputAddressEntry6.set_sensitive(False)
        self.ipInputMaskEntry6.set_sensitive(False)
        self.ipInputGatewayEntry6.set_sensitive(False)
        self.prymary_dnsEntry6.set_sensitive(False)
        self.searchEntry6.set_sensitive(False)

        gridOne6 = Gtk.Grid()
        gridOne6.set_column_homogeneous(True)
        gridOne6.set_row_homogeneous(False)
        gridOne6.set_column_spacing(5)
        gridOne6.set_row_spacing(10)
        gridOne6.attach(interfaceBox6, 0, 0, 4, 1)
        gridOne6.attach(radioBox6, 0, 1, 4, 1)
        gridOne6.attach(ipInputBox6, 0, 2, 4, 1)
        gridOne6.attach(ipEntryBox6, 0, 3, 4, 1)
        gridOne6.attach(dnsEntryBox6, 0, 4, 4, 1)
        gridOne6.attach(searchBox6, 0, 5, 4, 1)
        gridOne6.set_sensitive(False)

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
        cancelButton = Gtk.Button(label="Cancel")
        cancelButton.set_margin_bottom(10)
        cancelButton.connect("clicked", self.discard_pending_changes)
        buttonsWindow = Gtk.Box(orientation=0, spacing=10)
        buttonsWindow.pack_start(self.saveButton, False, False, 0)
        buttonsWindow.pack_start(cancelButton, False, False, 0)

        # Apply Tab 1 content and formatting to the notebook
        nb.append_page(gridOne)
        nb.set_tab_label_text(gridOne, "IPv4 Settings")

        # Apply Tab 2 content and formatting to the notebook
        nb.append_page(gridOne6)
        nb.set_tab_label_text(gridOne6, "IPv6 Settings WIP")
        # Put all the widgets together into one window
        mainBox = Gtk.Box(orientation=1, spacing=0)
        mainBox.pack_start(nb, True, True, 0)
        mainBox.pack_end(buttonsWindow, False, False, 0)
        self.add(mainBox)

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
        self.prymary_dnsEntry.set_text(self.currentSettings["DNS Server 1"])
        self.secondary_dnsEntry.set_text(self.currentSettings["DNS Server 2"])
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
        defaultrouter = self.ipInputGatewayEntry.get_text()
        if self.method == 'Manual':
            if 'wlan' in nic:
                ifconfig_nic = f'ifconfig_{nic}="WPA inet {inet} netmask {netmask}"\n'
            else:
                ifconfig_nic = f'ifconfig_{nic}="inet {inet} netmask {netmask}"\n'
            self.update_rc_conf(ifconfig_nic)
            defaultrouter_line = f'defaultrouter="{defaultrouter}"\n'
            self.update_rc_conf(defaultrouter_line)
            start_static_network(nic, inet, netmask)
            resolv_conf = open('/etc/resolv.conf', 'w')
            resolv_conf.writelines('# Generated by NetworkMgr\n')
            search = self.searchEntry.get_text()
            if search:
                search_line = f'search {search}\n'
                resolv_conf.writelines(search_line)
            dns1 = self.prymary_dnsEntry.get_text()
            nameserver1_line = f'nameserver {dns1}\n'
            resolv_conf.writelines(nameserver1_line)
            dns2 = self.secondary_dnsEntry.get_text()
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
                defaultrouter_line = f'defaultrouter="{defaultrouter}"\n'
                self.remove_rc_conf_line(defaultrouter_line)
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
    win = netCardConfigWindow(default_int)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    win.set_keep_above(True)
    Gtk.main()


def network_card_configuration_window():
    win = netCardConfigWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    win.set_keep_above(True)
    Gtk.main()
