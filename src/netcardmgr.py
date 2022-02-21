#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from subprocess import Popen, PIPE, check_output
import os
import re
# import subprocess
from time import sleep

ncard = 'ifconfig -l'
nics = Popen(ncard, shell=True, stdout=PIPE, close_fds=True,
             universal_newlines=True)
netcard = nics.stdout.readlines()[0].rstrip()
wifis = 'sysctl -in net.wlan.devices'
wifinics = Popen(wifis, shell=True, stdout=PIPE, close_fds=True,
                 universal_newlines=True)
wifiscard = wifinics.stdout.readlines()[0].rstrip()
rcconf = open('/etc/rc.conf', 'r').read()
if os.path.exists('/etc/rc.conf.local'):
    rcconflocal = open('/etc/rc.conf.local', 'r').read()
else:
    rcconflocal = "None"

notnics = [
    "enc",
    "lo",
    "fwe",
    "fwip",
    "tap",
    "plip",
    "pfsync",
    "pflog",
    "ipfw",
    "tun",
    "sl",
    "faith",
    "ppp",
    "bridge",
    "ixautomation",
    "vm-ixautomation",
    "wg"
]

cmd = "kenv | grep rc_system"
rc_system = Popen(cmd, shell=True, stdout=PIPE, universal_newlines=True)
if 'openrc' in rc_system.stdout.read():
    openrc = True
    rc = 'rc-'
    network = 'network'
else:
    openrc = False
    rc = ''
    network = 'netif'

restart_network = f'{rc}service {network} restart'

currentSettings = {}


class netCardConfigWindow(Gtk.Window):

    def edit_ipv4_setting(self, widget, value):
        if value == "DHCP":
            self.ipInputAddressEntry.set_sensitive(False)
            self.ipInputMaskEntry.set_sensitive(False)
            self.ipInputGatewayEntry.set_sensitive(False)
            self.dnsEntry.set_sensitive(False)
            self.searchEntry.set_sensitive(False)
            self.saveButton.set_sensitive(False)
        else:
            self.ipInputAddressEntry.set_sensitive(True)
            self.ipInputMaskEntry.set_sensitive(True)
            self.ipInputGatewayEntry.set_sensitive(True)
            self.dnsEntry.set_sensitive(True)
            self.searchEntry.set_sensitive(True)
            self.saveButton.set_sensitive(True)

    def __init__(self, defaultactiveint):
        # Build Default Window
        Gtk.Window.__init__(self, title="Network Interface Configuration")
        self.set_default_size(475, 400)

        # Build Tab 1 Content

        # Interface Drop Down Combo Box
        cell = Gtk.CellRendererText()

        interfaceComboBox = Gtk.ComboBox()
        interfaceComboBox.pack_start(cell, expand=True)
        interfaceComboBox.add_attribute(cell, 'text', 0)

        # Add interfaces to a ListStore
        store = Gtk.ListStore(str)
        validinterfaces = self.enumerate_nics()
        for validinterface in validinterfaces:
            store.append([validinterface])

        # Build the UI aspects of the ComboBox, passing the interface clicked in the trayicon
        # as the interface that needs to be the active one when the combo box is drawn
        activeComboBoxObjectIndex = validinterfaces.index(f"{defaultactiveint}")
        interfaceComboBox.set_model(store)
        interfaceComboBox.set_margin_top(15)
        interfaceComboBox.set_margin_end(30)
        interfaceComboBox.set_active(activeComboBoxObjectIndex)
        self.cbox_config_refresh(interfaceComboBox)
        interfaceComboBox.connect("changed", self.cbox_config_refresh)

        # Build Label to sit in front of the ComboBox
        labelOne = Gtk.Label(label="Interface:")
        labelOne.set_margin_top(15)
        labelOne.set_margin_start(30)

        # Add both objects to a single box, which will then be added to the grid
        interfaceBox = Gtk.Box(orientation=0, spacing=100)
        interfaceBox.pack_start(labelOne, False, False, 0)
        interfaceBox.pack_end(interfaceComboBox, True, True, 0)

        # Add radio button to toggle DHCP or not
        rb_dhcp4 = Gtk.RadioButton.new_with_label(None, "DHCP")
        rb_dhcp4.set_margin_top(15)
        rb_dhcp4.connect("toggled", self.edit_ipv4_setting, "DHCP")
        rb_manual4 = Gtk.RadioButton.new_with_label_from_widget(rb_dhcp4, "Manual")
        rb_manual4.set_margin_top(15)
        rb_manual4.connect("toggled", self.edit_ipv4_setting, "Manual")
        if currentSettings["Address Assignment Method"] == "DHCP":
            rb_dhcp4.set_active(True)
        else:
            rb_manual4.set_active(True)
        rb_manual4.join_group(rb_dhcp4)

        radioButtonLabel = Gtk.Label(label="IPv4 Method:")
        radioButtonLabel.set_margin_top(15)
        radioButtonLabel.set_margin_start(30)

        radioBox = Gtk.Box(orientation=0, spacing=50)
        radioBox.set_homogeneous(False)
        radioBox.pack_start(radioButtonLabel, False, False, 0)
        radioBox.pack_start(rb_dhcp4, True, False, 0)
        radioBox.pack_end(rb_manual4, True, True, 0)

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
        dnsLabel = Gtk.Label(label="DNS Servers: ")
        dnsLabel.set_margin_top(15)
        dnsLabel.set_margin_end(58)
        dnsLabel.set_margin_start(30)

        self.dnsEntry = Gtk.Entry()
        self.dnsEntry.set_margin_end(30)
        DNSList = [(key, value) for key, value in currentSettings.items() if key.startswith("DNS Server")]
        print(DNSList)
        i = 0
        DNSString = ""
        while i < len(DNSList):
            DNSString = DNSString + DNSList[i][1]
            if i + 1 < len(DNSList):
                DNSString = DNSString + ","
            i = i + 1
        self.dnsEntry.set_text(DNSString)

        dnsEntryBox = Gtk.Box(orientation=0, spacing=0)
        dnsEntryBox.pack_start(dnsLabel, False, False, 0)
        dnsEntryBox.pack_end(self.dnsEntry, True, True, 0)

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
        if currentSettings["Address Assignment Method"] == "DHCP":
            self.ipInputAddressEntry.set_sensitive(False)
            self.ipInputMaskEntry.set_sensitive(False)
            self.ipInputGatewayEntry.set_sensitive(False)
            self.dnsEntry.set_sensitive(False)
            self.searchEntry.set_sensitive(False)
        # Build the grid, which will handle the physical layout of the UI elements.
        gridOne = Gtk.Grid()
        gridOne.set_column_homogeneous(True)
        gridOne.set_row_homogeneous(False)
        gridOne.set_column_spacing(5)
        gridOne.set_row_spacing(10)
        gridOne.attach(interfaceBox, 0, 0, 4, 1)
        gridOne.attach(radioBox, 0, 1, 4, 1)
        gridOne.attach(ipInputBox, 0, 2, 4, 1)
        gridOne.attach(ipEntryBox, 0, 3, 4, 1)
        gridOne.attach(dnsEntryBox, 0, 4, 4, 1)
        gridOne.attach(searchBox, 0, 5, 4, 1)

        # Build Tab 2 Content

        # Interface Drop Down Combo Box
        cell6 = Gtk.CellRendererText()

        interfaceComboBox6 = Gtk.ComboBox()
        interfaceComboBox6.pack_start(cell6, expand=True)
        interfaceComboBox6.add_attribute(cell6, 'text', 0)

        # Add interfaces to a ListStore
        store6 = Gtk.ListStore(str)
        validinterfaces6 = self.enumerate_nics()
        for validinterface6 in validinterfaces6:
            store6.append([validinterface6])

        # Build the UI aspects of the ComboBox, passing the interface clicked in the trayicon
        # as the interface that needs to be the active one when the combo box is drawn
        activeComboBoxObjectIndex6 = validinterfaces6.index(f"{defaultactiveint}")
        interfaceComboBox6.set_model(store)
        interfaceComboBox6.set_margin_top(15)
        interfaceComboBox6.set_margin_end(30)
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
        rb_manual6 = Gtk.RadioButton.new_with_label_from_widget(rb_slaac6, "Manual")
        rb_manual6.set_margin_top(15)
        rb_manual6.join_group(rb_slaac6)

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
        dnsLabel6 = Gtk.Label(label="DNS Servers: ")
        dnsLabel6.set_margin_top(15)
        dnsLabel6.set_margin_end(58)
        dnsLabel6.set_margin_start(30)

        self.dnsEntry6 = Gtk.Entry()
        self.dnsEntry6.set_margin_end(30)

        dnsEntryBox6 = Gtk.Box(orientation=0, spacing=0)
        dnsEntryBox6.pack_start(dnsLabel6, False, False, 0)
        dnsEntryBox6.pack_end(self.dnsEntry6, True, True, 0)

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
        self.dnsEntry6.set_sensitive(False)
        self.searchEntry6.set_sensitive(False)
        # Build the grid, which will handle the physical layout of the UI elements.
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

        # Build Notebook

        nb = Gtk.Notebook()
        nb.set_margin_start(10)
        nb.set_margin_end(10)
        nb.set_margin_top(10)
        nb.set_margin_bottom(10)
        nb.set_tab_pos(2)

        # Build Save & Cancel Buttons

        self.saveButton = Gtk.Button(label="Save...")
        self.saveButton.set_margin_bottom(10)
        self.saveButton.set_margin_start(10)
        self.saveButton.connect("clicked", self.commit_pending_changes)
        if currentSettings["Address Assignment Method"] == "DHCP":
            self.saveButton.set_sensitive(False)
        cancelButton = Gtk.Button(label="Cancel...")
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
        nb.set_tab_label_text(gridOne6, "IPv6 Settings")

        # Put all the widgets together into one window
        mainBox = Gtk.Box(orientation=1, spacing=0)
        mainBox.pack_start(nb, False, False, 0)
        mainBox.pack_start(buttonsWindow, False, False, 0)
        self.add(mainBox)

        # Run any functions that need to execute once at window creation
        self.cbox_config_refresh(interfaceComboBox)

    # Returns a list of valid configurable interfaces.
    def enumerate_nics(self):
        validnics = list()
        confnotnics = ["lo", "fwe", "fwip", "tap", "plip", "pfsync", "pflog",
                       "tun", "sl", "faith", "ppp", "bridge", "ixautomation"]
        confncard = 'ifconfig -l'
        confnics = Popen(confncard, shell=True, stdout=PIPE, close_fds=True, universal_newlines=True)
        confnetcard = confnics.stdout.readlines()[0].rstrip()
        confnetcardarray = confnetcard.split(" ")
        for confnic in confnetcardarray:
            nicgeneralized = re.findall("[a-zA-Z]+", confnic)
            stringnicgeneralized = str(nicgeneralized).replace("'", "")
            stringnicgeneralized = stringnicgeneralized.replace("[", "")
            stringnicgeneralized = stringnicgeneralized.replace("]", "")
            if stringnicgeneralized in confnotnics:
                print(f"{confnic} was generalized to {nicgeneralized} and was found in the notnics list! "
                      "It will not be added to the valid configurable nic list in the netCardConfigWindow.enumerate_nics method.")
            else:
                validnics.append(confnic)
        return(validnics)

    # Used with the combo box to refresh the UI of tab 1 with active settings for the newly selected active interface.
    def cbox_config_refresh(self, widget):
        refreshedInterface = widget.get_active()
        refreshedInterfaceName = self.enumerate_nics()[refreshedInterface]
        # actions here need to refresh the values on the first two tabs.
        print(f"Refreshing settings to match current settings on {refreshedInterface}. "
              f"Interface name is {refreshedInterfaceName}")
        self.get_current_interface_settings(refreshedInterfaceName)
        self.display_current_interface_settings(widget)

    def get_current_interface_settings(self, active_nic):
        # Need to accurately determine if a wlanN interface is using DHCP
        aInt = str(active_nic)

        DHCPStatus = os.path.exists(f"/var/db/dhclient.leases.{aInt}")
        print(f"dhcpstatus return value = {DHCPStatus}")
        if DHCPStatus is False:
            RCConf = open("/etc/rc.conf", "r").read()
            DHCPSearch = re.findall(f"^ifconfig_{aInt}=\".*DHCP", RCConf)
            print(f"DHCPSearch is {DHCPSearch} and the length is {len(DHCPSearch)}")
            if len(DHCPSearch) < 1:
                DHCPStatusOutput = "Manual"
            else:
                DHCPStatusOutput = "DHCP"
        else:
            DHCPStatusOutput = "DHCP"

        print(f"DHCPStatusOutput = {DHCPStatusOutput}")

        ifconfigaInt = f"ifconfig -f inet:dotted {aInt}"
        ifconfigaIntOutput = check_output(ifconfigaInt.split(" "))

        aIntIP = re.findall(r'inet [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+', str(ifconfigaIntOutput))[0]
        aIntIPStrip = str(aIntIP).replace("inet ", "")
        aIntIPStrip = str(aIntIPStrip).replace("'", "")
        aIntIPStrip = str(aIntIPStrip).replace("[", "")
        aIntIPStrip = str(aIntIPStrip).replace("]", "")
        aIntMask = re.findall(r'netmask [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+', str(ifconfigaIntOutput))[0]
        aIntMaskStrip = str(aIntMask).replace("netmask ", "")
        aIntMaskStrip = str(aIntMaskStrip).replace("'", "")
        aIntMaskStrip = str(aIntMaskStrip).replace("[", "")
        aIntMaskStrip = str(aIntMaskStrip).replace("]", "")
        aIntBroadcast = re.findall(r'broadcast [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+', str(ifconfigaIntOutput))[0]
        aIntBroadcastStrip = str(aIntBroadcast).replace("broadcast ", "")
        aIntBroadcastStrip = str(aIntBroadcastStrip).replace("'", "")
        aIntBroadcastStrip = str(aIntBroadcastStrip).replace("[", "")
        aIntBroadcastStrip = str(aIntBroadcastStrip).replace("]", "")

        if (DHCPStatusOutput == "DHCP"):
            print(f"{DHCPStatusOutput}")
            DHClientFileTest = os.path.exists(f"/var/db/dhclient.leases.{aInt}")
            if DHClientFileTest is False:
                print(f"dhclientfiletest = {DHClientFileTest}")
                # RenewDHCP = f"dhclient {aInt}"
                # RenewDHCPOutput = subprocess.check_output(RenewDHCP.split(" "))
                sleep(5)
                DHClientFileTest = os.path.exists(f"/var/db/dhclient.leases.{aInt}")
                if DHClientFileTest is False:
                    print(f"DHCP is enabled, but we're unable to read the lease file a /var/db/dhclient.leases.{aInt}")
                    aIntGatewayStrip = ""
            else:
                DHCPLeaseInfo = open(f"/var/db/dhclient.leases.{aInt}", "r").read()
                aIntGateway = re.findall(r"option routers [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+;", DHCPLeaseInfo)[0]
                aIntGatewayStrip = str(aIntGateway).replace("option routers ", "")
                aIntGatewayStrip = str(aIntGatewayStrip).replace("'", "")
                aIntGatewayStrip = str(aIntGatewayStrip).replace("[", "")
                aIntGatewayStrip = str(aIntGatewayStrip).replace("]", "")
                aIntGatewayStrip = str(aIntGatewayStrip).replace(";", "")

                # aIntDHCP = f"resolvconf -l {aInt}"
                # aIntDHCPResults = subprocess.check_output(aIntDHCP.split(" "))
                # aIntDHCPResults = subprocess.run(aIntDHCP.split(" "),
                #                                  capture_output=True,
                #                                  text=True)
                # DNSMatch = re.findall(r'nameserver [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+', str(aIntDHCPResults))
                DefaultDNSServers = open('/etc/resolv.conf').read()
                DNSMatch = re.findall(r'nameserver [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+', str(DefaultDNSServers))

                SearchDomainMatch = re.findall('search [a-zA-Z.]*', str(DefaultDNSServers))
                if len(SearchDomainMatch) < 1:
                    RCConfDomainSearch = open('/etc/resolv.conf', 'r').read()
                    SearchDomainMatch = re.findall('domain (.*)', RCConfDomainSearch)
                SearchDomainMatchStrip = str(SearchDomainMatch).replace("domain ", "")
                SearchDomainMatchStrip = str(SearchDomainMatchStrip).replace("'", "")
                SearchDomainMatchStrip = str(SearchDomainMatchStrip).replace("[", "")
                SearchDomainMatchStrip = str(SearchDomainMatchStrip).replace("]", "")
        else:
            RRConfGatewaySearch = open('/etc/rc.conf', 'r').read()
            RRConfGatewayResults = re.findall(r'defaultrouter="[0-9]+\.[0-9]+\.[0-9]+\.[0-9]"', RRConfGatewaySearch)
            aIntGatewayStrip = str(RRConfGatewayResults).replace('defaultrouter="', "")
            aIntGatewayStrip = str(aIntGatewayStrip).replace('"', "")
            aIntGatewayStrip = str(aIntGatewayStrip).replace('[', "")
            aIntGatewayStrip = str(aIntGatewayStrip).replace(']', "")
            aIntGatewayStrip = str(aIntGatewayStrip).replace("'", "")

            DefaultDNSServers = open('/etc/resolv.conf').read()
            DNSMatch = re.findall(r'nameserver [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+', str(DefaultDNSServers))

            RCConfDomainSearch = open('/etc/resolv.conf', 'r').read()
            SearchDomainMatch = re.findall('domain (.*)', RCConfDomainSearch)
            SearchDomainMatchStrip = str(SearchDomainMatch).replace("domain ", "")
            SearchDomainMatchStrip = str(SearchDomainMatchStrip).replace("'", "")
            SearchDomainMatchStrip = str(SearchDomainMatchStrip).replace("[", "")
            SearchDomainMatchStrip = str(SearchDomainMatchStrip).replace("]", "")

        # currentSettings = {}
        currentSettings["Active Interface"] = active_nic
        currentSettings["Address Assignment Method"] = DHCPStatusOutput
        currentSettings["Interface IP"] = aIntIPStrip
        currentSettings["Interface Subnet Mask"] = aIntMaskStrip
        currentSettings["Broadcast Address"] = aIntBroadcastStrip
        currentSettings["Default Gateway"] = aIntGatewayStrip
        # [currentSettings.append(str(DNSServer).replace("nameserver ", "")) for DNSServer in DNSMatch]
        currentSettings["Search Domain"] = SearchDomainMatchStrip
        i = 1
        while i <= len(DNSMatch):
            currentSettings[f"DNS Server {i}"] = str(DNSMatch[(i - 1)]).replace("nameserver ", "")
            i = i + 1

        print("Current settings are below:")
        print(f"{currentSettings}")

    def display_current_interface_settings(self, widget):
        print("display_current_interface_settings_go_here")

    def commit_pending_changes(self, widget):
        print("commit_pending_changes_goes_here")

    def discard_pending_changes(self, widget):
        print("discard_pending_changes_goes_here")
        self.destroy()


def openNetCardConfigwindow(default_int):
    win = netCardConfigWindow(default_int)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
