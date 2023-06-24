#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from subprocess import check_output, run
import os
import re
from net_api import (
    start_static_network,
    nics_list,
    defaultcard,
    restart_dhcp_network
)
rcconf = open('/etc/rc.conf', 'r').read()
if os.path.exists('/etc/rc.conf.local'):
    rcconflocal = open('/etc/rc.conf.local', 'r').read()
else:
    rcconflocal = "None"

global currentSettings
currentSettings = {}


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
            if self.method == currentSettings["Assignment Method"]:
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

    def __init__(self, selected_nic=None):
        # Build Default Window
        Gtk.Window.__init__(self, title="Network Interface Configuration")
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
        self.get_current_interface_settings(DEFAULT_NIC)
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
        self.version = currentSettings["Assignment Method"]
        self.rb_dhcp4 = Gtk.RadioButton.new_with_label(None, "DHCP")
        self.rb_dhcp4.set_margin_top(15)
        self.rb_manual4 = Gtk.RadioButton.new_with_label_from_widget(
            self.rb_dhcp4, "Manual")
        self.rb_manual4.set_margin_top(15)
        if currentSettings["Assignment Method"] == "DHCP":
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
        self.ipInputAddressEntry.set_text(currentSettings["Interface IP"])

        self.ipInputMaskEntry = Gtk.Entry()
        self.ipInputMaskEntry.set_text(currentSettings["Interface Subnet Mask"])

        self.ipInputGatewayEntry = Gtk.Entry()
        self.ipInputGatewayEntry.set_margin_end(15)
        self.ipInputGatewayEntry.set_text(currentSettings["Default Gateway"])

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
        self.prymary_dnsEntry.set_text(currentSettings["DNS Server 1"])

        self.secondary_dnsEntry = Gtk.Entry()
        self.secondary_dnsEntry.set_margin_end(30)
        self.secondary_dnsEntry.set_text(currentSettings["DNS Server 2"])

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
        self.searchEntry.set_text(currentSettings["Search Domain"])

        searchBox = Gtk.Box(orientation=0, spacing=0)
        searchBox.pack_start(searchLabel, False, False, 0)
        searchBox.pack_end(self.searchEntry, True, True, 0)

        self.rb_dhcp4.connect("toggled", self.edit_ipv4_setting)
        self.rb_manual4.connect("toggled", self.edit_ipv4_setting)

        if currentSettings["Assignment Method"] == "DHCP":
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
        self.ipInputMaskEntry6 = Gtk.Entry()
        self.ipInputGatewayEntry6 = Gtk.Entry()
        self.ipInputGatewayEntry6.set_margin_end(15)

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
        if currentSettings["Assignment Method"] == "DHCP":
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
        self.get_current_interface_settings(nics[widget.get_active()])
        self.update_interface_settings()

    def get_current_interface_settings(self, active_nic):
        # Need to accurately determine if a wlanN interface is using DHCP

        rc_conf = open("/etc/rc.conf", "r").read()
        DHCPSearch = re.findall(fr'^ifconfig_{active_nic}=".*DHCP', rc_conf, re.MULTILINE)
        print(f"DHCPSearch is {DHCPSearch} and the length is {len(DHCPSearch)}")
        if len(DHCPSearch) < 1:
            DHCPStatusOutput = "Manual"
        else:
            DHCPStatusOutput = "DHCP"

        IPREGEX = r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+'

        ifcmd = f"ifconfig -f inet:dotted {active_nic}"
        ifoutput = check_output(ifcmd.split(" "), universal_newlines=True)
        re_ip = re.search(fr'inet {IPREGEX}', ifoutput)
        if_ip = re_ip.group().replace("inet ", "").strip()
        re_netmask = re.search(fr'netmask {IPREGEX}', ifoutput)
        if_netmask = re_netmask.group().replace("netmask ", "").strip()
        re_broadcast = re.search(fr'broadcast {IPREGEX}', ifoutput)
        if_broadcast = re_broadcast.group().replace("broadcast ", "").strip()
        if (DHCPStatusOutput == "DHCP"):
            dhclient_leases = f"/var/db/dhclient.leases.{active_nic}"

            if os.path.exists(dhclient_leases) is False:
                print("DHCP is enabled, but we're unable to read the lease "
                      f"file a /var/db/dhclient.leases.{active_nic}")
                gateway = ""
            else:
                dh_lease = open(dhclient_leases, "r").read()
                re_gateway = re.search(fr"option routers {IPREGEX}", dh_lease)
                gateway = re_gateway.group().replace("option routers ", "")
        else:
            rc_conf = open('/etc/rc.conf', 'r').read()
            re_gateway = re.search(fr'^defaultrouter="{IPREGEX}"', rc_conf, re.MULTILINE)
            gateway = re_gateway.group().replace('"', "")
            gateway = gateway.replace('defaultrouter=', "")

        if os.path.exists('/etc/resolv.conf'):
            resolv_conf = open('/etc/resolv.conf').read()
            nameservers = re.findall(fr'^nameserver {IPREGEX}', str(resolv_conf), re.MULTILINE)
            print(nameservers)

            re_domain_search = re.findall('search [a-zA-Z.]*', str(resolv_conf))
            if len(re_domain_search) < 1:
                re_domain_search = re.findall('domain (.*)', resolv_conf)
            domain_search = str(re_domain_search).replace("domain ", "")
            domain_search = domain_search.replace("'", "")
            domain_search = domain_search.replace("[", "")
            domain_search = domain_search.replace("]", "")
            domain_search = domain_search.replace('search', '').strip()
        else:
            domain_search = ''
            nameservers = []

        currentSettings["Active Interface"] = active_nic
        currentSettings["Assignment Method"] = DHCPStatusOutput
        currentSettings["Interface IP"] = if_ip
        currentSettings["Interface Subnet Mask"] = if_netmask
        currentSettings["Broadcast Address"] = if_broadcast
        currentSettings["Default Gateway"] = gateway
        currentSettings["Search Domain"] = domain_search

        for num in range(len(nameservers)):
            currentSettings[
                f"DNS Server {num + 1}"
            ] = str(nameservers[(num)]).replace("nameserver", "").strip()

        print("Current settings are below:")
        print(f"{currentSettings}")

    def update_interface_settings(self):
        self.ipInputAddressEntry.set_text(currentSettings["Interface IP"])
        self.ipInputMaskEntry.set_text(currentSettings["Interface Subnet Mask"])
        self.ipInputGatewayEntry.set_text(currentSettings["Default Gateway"])
        self.prymary_dnsEntry.set_text(currentSettings["DNS Server 1"])
        self.secondary_dnsEntry.set_text(currentSettings["DNS Server 2"])
        self.searchEntry.set_text(currentSettings["Search Domain"])
        if currentSettings["Assignment Method"] == "DHCP":
            self.rb_dhcp4.set_active(True)
        else:
            self.rb_manual4.set_active(True)

    def commit_pending_changes(self, widget):
        nic = currentSettings["Active Interface"]
        inet = self.ipInputAddressEntry.get_text()
        netmask = self.ipInputMaskEntry.get_text()
        defaultrouter = self.ipInputGatewayEntry.get_text()
        if self.method == 'Manual':
            ifconfig_nic = f'ifconfig_{nic}="inet {inet} netmask {netmask}"\n'
            self.update_rc_conf(ifconfig_nic)
            defaultrouter_line = f'defaultrouter="{defaultrouter}"\n'
            self.update_rc_conf(defaultrouter_line)

            resolv_conf = open('/etc/resolv.conf', 'w')
            resolv_conf.writelines('# Generated by NetworkMgr\n')
            search = self.searchEntry.get_text()
            search_line = f'search {search}\n'
            resolv_conf.writelines(search_line)
            dns1 = self.prymary_dnsEntry.get_text()
            nameserver1_line = f'nameserver {dns1}\n'
            resolv_conf.writelines(nameserver1_line)
            dns2 = self.secondary_dnsEntry.get_text()
            nameserver2_line = f'nameserver {dns2}\n'
            resolv_conf.writelines(nameserver2_line)
            resolv_conf.close()
            start_static_network(nic, inet, netmask)
        else:
            ifconfig_nic = f'ifconfig_{nic}="DHCP"\n'
            self.update_rc_conf(ifconfig_nic)

            rc_conf = open('/etc/rc.conf', 'r').read()
            for nic_search in self.NICS:
                if re.search(f'^ifconfig_{nic_search}="inet', rc_conf, re.MULTILINE):
                    break
            else:
                defaultrouter_line = f'defaultrouter="{defaultrouter}"\n'
                self.remove_rc_conf_line(defaultrouter_line)
            restart_dhcp_network(nic)

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


# def openNetCardConfigwindow(default_int):
win = netCardConfigWindow('wlan0')
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()
