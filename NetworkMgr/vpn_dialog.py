#!/usr/bin/env python

"""GTK dialogs for importing, editing, and authenticating VPN connections.

Provides a NetworkManager-style file importer (.ovpn and .conf), a tabbed VPN
connection editor for OpenVPN and WireGuard (including IPv4/IPv6 static
addresses and static routes), and a credentials dialog for OpenVPN connections
that require username/password authentication at connect time.
"""

import gettext
import os
import gi
gi.require_version('Gtk', '3.0')
# pylint: disable=wrong-import-position
from gi.repository import Gtk, Pango

from NetworkMgr.openvpn_api import (
    AUTH_DIGEST_OPTIONS,
    CIPHER_OPTIONS,
    OPENVPN_NOT_INSTALLED_MSG,
    default_openvpn_config,
    detect_vpn_file_type,
    is_openvpn_installed,
    parse_openvpn_config,
    save_openvpn_config,
)
from NetworkMgr.wg_api import (
    default_wireguard_config,
    parse_wireguard_config,
    sanitize_wg_id,
    save_wireguard_config,
)

gettext.bindtextdomain('NetworkMgr', '/usr/local/share/locale')
gettext.textdomain('NetworkMgr')
_ = gettext.gettext


def _bold_label(text):
    """Create a bold section heading label without Pango markup."""
    label = Gtk.Label(label=text)
    label.set_halign(Gtk.Align.START)
    attrs = Pango.AttrList()
    attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
    label.set_attributes(attrs)
    return label


def _field_label(text):
    """Create a right-aligned form field label."""
    label = Gtk.Label(label=text)
    label.set_halign(Gtk.Align.END)
    return label


def _show_error_dialog(parent, title, message):
    """Display a modal GTK error message dialog."""
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=title,
    )
    dialog.format_secondary_text(message)
    dialog.run()
    dialog.destroy()


def show_openvpn_not_installed_alert(parent=None):
    """Show an English alert dialog informing the user that OpenVPN is not installed."""
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.OK,
        text="OpenVPN is not installed",
    )
    dialog.format_secondary_text(OPENVPN_NOT_INSTALLED_MSG)
    dialog.run()
    dialog.destroy()


def import_vpn_file_dialog(parent=None, on_saved=None):
    """Open a FileChooserDialog to import an OpenVPN or WireGuard config file.

    Automatically detects whether the chosen file is an OpenVPN (.ovpn/.conf)
    or WireGuard (.conf) configuration, parses all settings and inline
    certificates, and opens the VPNConnectionDialog pre-populated with the
    imported configuration.

    Args:
        parent (Gtk.Window or None): optional transient parent window.
        on_saved (callable or None): callback invoked as on_saved(profile_id, vpn_type)
            after the user saves the imported connection.
    """
    chooser = Gtk.FileChooserDialog(
        title=_("Import VPN Configuration"),
        transient_for=parent,
        action=Gtk.FileChooserAction.OPEN,
    )
    chooser.add_buttons(
        Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
        Gtk.STOCK_OPEN, Gtk.ResponseType.ACCEPT,
    )

    vpn_filter = Gtk.FileFilter()
    vpn_filter.set_name(_("VPN Configurations (*.ovpn, *.conf)"))
    vpn_filter.add_pattern("*.ovpn")
    vpn_filter.add_pattern("*.conf")
    chooser.add_filter(vpn_filter)

    ovpn_filter = Gtk.FileFilter()
    ovpn_filter.set_name(_("OpenVPN Configurations (*.ovpn, *.conf)"))
    ovpn_filter.add_pattern("*.ovpn")
    ovpn_filter.add_pattern("*.conf")
    chooser.add_filter(ovpn_filter)

    all_filter = Gtk.FileFilter()
    all_filter.set_name(_("All Files (*)"))
    all_filter.add_pattern("*")
    chooser.add_filter(all_filter)

    response = chooser.run()
    filepath = chooser.get_filename()
    chooser.destroy()

    if response != Gtk.ResponseType.ACCEPT or not filepath:
        return

    try:
        vpn_type = detect_vpn_file_type(filepath)
        if vpn_type == 'wireguard':
            cfg = parse_wireguard_config(filepath)
        else:
            if not is_openvpn_installed():
                show_openvpn_not_installed_alert(parent)
            cfg = parse_openvpn_config(filepath)
    except ValueError as err:
        _show_error_dialog(
            parent,
            _("Could not import VPN configuration"),
            str(err),
        )
        return

    editor = VPNConnectionDialog(cfg, parent=parent, on_saved=on_saved)
    editor.show_all()
    editor.refresh_dynamic_visibility()


class VPNConnectionDialog(Gtk.Window):
    """NetworkManager-style VPN connection editor for OpenVPN and WireGuard."""

    AUTH_TYPES = [
        ('tls', _("Certificates (TLS)")),
        ('password', _("Password")),
        ('tls-password', _("Certificates with Password (TLS)")),
        ('static-key', _("Static Key")),
    ]

    COMPRESS_TYPES = [
        ('', _("None")),
        ('comp-lzo-adaptive', _("LZO Adaptive (comp-lzo)")),
        ('comp-lzo-yes', _("LZO (comp-lzo yes)")),
        ('comp-lzo-no', _("LZO Disabled (comp-lzo no)")),
        ('lzo', _("LZO (compress lzo)")),
        ('lz4', _("LZ4 (compress lz4)")),
        ('lz4-v2', _("LZ4 v2 (compress lz4-v2)")),
        ('stub-v2', _("Framing only (stub-v2)")),
    ]

    TLS_MODES = [
        ('none', _("None")),
        ('tls-auth', _("TLS-Auth")),
        ('tls-crypt', _("TLS-Crypt")),
        ('tls-crypt-v2', _("TLS-Crypt v2")),
    ]

    def __init__(self, cfg=None, parent=None, on_saved=None):
        super().__init__(title=_("VPN Connection Editor"))
        if parent is not None:
            self.set_transient_for(parent)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(660, 560)
        self.set_border_width(12)

        self.cfg = cfg if cfg is not None else default_openvpn_config()
        self.vpn_type = self.cfg.get('vpn_type', 'openvpn')
        self.on_saved = on_saved
        self.auth_rows = {}
        self.tls_key_rows = ()
        self.proxy_rows = ()
        self._wg_id_auto = True

        main_box = Gtk.VBox(spacing=10)
        self.add(main_box)

        # Header: Connection Name and VPN Type
        header_grid = Gtk.Grid()
        header_grid.set_column_spacing(10)
        header_grid.set_row_spacing(8)
        main_box.pack_start(header_grid, False, False, 0)

        name_lbl = _field_label(_("Connection Name:"))
        header_grid.attach(name_lbl, 0, 0, 1, 1)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_hexpand(True)
        self.name_entry.set_text(self.cfg.get('name', ''))
        header_grid.attach(self.name_entry, 1, 0, 2, 1)

        type_lbl = _field_label(_("VPN Type:"))
        header_grid.attach(type_lbl, 0, 1, 1, 1)
        type_val_lbl = Gtk.Label(
            label="WireGuard" if self.vpn_type == 'wireguard' else "OpenVPN"
        )
        type_val_lbl.set_halign(Gtk.Align.START)
        header_grid.attach(type_val_lbl, 1, 1, 2, 1)

        if self.vpn_type == 'wireguard':
            self._build_wireguard_notebook(main_box)
            self.name_entry.connect("changed", self._on_wg_name_changed)
        else:
            self._build_openvpn_notebook(main_box)

        # Bottom action buttons
        btn_box = Gtk.HBox(spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        main_box.pack_end(btn_box, False, False, 0)

        cancel_btn = Gtk.Button(label=_("Cancel"))
        cancel_btn.connect("clicked", lambda _w: self.destroy())
        btn_box.pack_start(cancel_btn, False, False, 0)

        save_btn = Gtk.Button(label=_("Save"))
        save_btn.connect("clicked", self.on_save_clicked)
        btn_box.pack_start(save_btn, False, False, 0)

    def _on_wg_name_changed(self, entry):
        """Sync WireGuard tunnel ID when Connection Name changes unless manually edited."""
        if self._wg_id_auto and hasattr(self, 'wg_id_entry'):
            self.wg_id_entry.handler_block_by_func(self._on_wg_id_edited)
            self.wg_id_entry.set_text(sanitize_wg_id(entry.get_text()))
            self.wg_id_entry.handler_unblock_by_func(self._on_wg_id_edited)

    def _on_wg_id_edited(self, _entry):
        """Mark WireGuard tunnel ID as manually edited."""
        self._wg_id_auto = False

    def _cert_picker_row(self, grid, row, label_text, path_key, inline_key, patterns):
        """Create a row with a status/file chooser for a certificate or key."""
        lbl = _field_label(label_text)
        grid.attach(lbl, 0, row, 1, 1)

        hbox = Gtk.HBox(spacing=6)
        status_label = Gtk.Label()
        status_label.set_halign(Gtk.Align.START)
        status_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        status_label.set_max_width_chars(28)

        if self.cfg.get(inline_key):
            status_label.set_text(_("Inline (extracted from profile)"))
        elif self.cfg.get(path_key):
            status_label.set_text(os.path.basename(self.cfg[path_key]))
        else:
            status_label.set_text(_("None selected"))

        chooser = Gtk.FileChooserButton(
            title=label_text,
            action=Gtk.FileChooserAction.OPEN,
        )
        file_filter = Gtk.FileFilter()
        file_filter.set_name(label_text)
        for pat in patterns:
            file_filter.add_pattern(pat)
        chooser.add_filter(file_filter)

        all_filter = Gtk.FileFilter()
        all_filter.set_name(_("All Files (*)"))
        all_filter.add_pattern("*")
        chooser.add_filter(all_filter)

        if self.cfg.get(path_key) and os.path.isfile(self.cfg[path_key]):
            chooser.set_filename(self.cfg[path_key])

        def _on_file_set(btn):
            chosen = btn.get_filename()
            if chosen:
                self.cfg[path_key] = chosen
                self.cfg[inline_key] = ''
                status_label.set_text(os.path.basename(chosen))

        chooser.connect("file-set", _on_file_set)
        hbox.pack_start(status_label, True, True, 0)
        hbox.pack_end(chooser, False, False, 0)
        grid.attach(hbox, 1, row, 2, 1)
        return (lbl, hbox)

    def _build_openvpn_notebook(self, main_box):
        """Build the OpenVPN configuration notebook (VPN, IPv4, IPv6, Advanced, Security, Proxies)."""
        notebook = Gtk.Notebook()
        main_box.pack_start(notebook, True, True, 0)

        # --- Tab 1: General / Authentication ---
        gen_grid = Gtk.Grid()
        gen_grid.set_border_width(12)
        gen_grid.set_column_spacing(10)
        gen_grid.set_row_spacing(8)
        row = 0

        gw_lbl = _field_label(_("Gateway:"))
        gen_grid.attach(gw_lbl, 0, row, 1, 1)
        self.gateway_entry = Gtk.Entry()
        self.gateway_entry.set_hexpand(True)
        self.gateway_entry.set_placeholder_text("vpn.example.com:1194:udp")
        self.gateway_entry.set_text(self.cfg.get('gateway', ''))
        gen_grid.attach(self.gateway_entry, 1, row, 2, 1)
        row += 1

        auth_lbl = _field_label(_("Authentication Type:"))
        gen_grid.attach(auth_lbl, 0, row, 1, 1)
        self.auth_type_combo = Gtk.ComboBoxText()
        current_auth = self.cfg.get('auth_type', 'tls')
        active_idx = 0
        for idx, (code, title) in enumerate(self.AUTH_TYPES):
            self.auth_type_combo.append(code, title)
            if code == current_auth:
                active_idx = idx
        self.auth_type_combo.set_active(active_idx)
        self.auth_type_combo.connect("changed", lambda _c: self.refresh_dynamic_visibility())
        gen_grid.attach(self.auth_type_combo, 1, row, 2, 1)
        row += 1

        # CA Certificate
        self.auth_rows['ca'] = self._cert_picker_row(
            gen_grid, row, _("CA Certificate:"), 'ca_path', 'ca_inline',
            ("*.pem", "*.crt", "*.cer"),
        )
        row += 1

        # User Certificate
        self.auth_rows['cert'] = self._cert_picker_row(
            gen_grid, row, _("User Certificate:"), 'cert_path', 'cert_inline',
            ("*.pem", "*.crt", "*.cer", "*.p12"),
        )
        row += 1

        # Private Key
        self.auth_rows['key'] = self._cert_picker_row(
            gen_grid, row, _("Private Key:"), 'key_path', 'key_inline',
            ("*.pem", "*.key", "*.p12"),
        )
        row += 1

        # Private Key Password
        key_pwd_lbl = _field_label(_("Key Password:"))
        gen_grid.attach(key_pwd_lbl, 0, row, 1, 1)
        key_pwd_box = Gtk.HBox(spacing=6)
        self.key_pwd_entry = Gtk.Entry()
        self.key_pwd_entry.set_visibility(False)
        self.key_pwd_entry.set_hexpand(True)
        self.key_pwd_entry.set_text(self.cfg.get('key_password', ''))
        key_pwd_show = Gtk.CheckButton(label=_("Show"))
        key_pwd_show.connect(
            "toggled",
            lambda w: self.key_pwd_entry.set_visibility(w.get_active())
        )
        key_pwd_box.pack_start(self.key_pwd_entry, True, True, 0)
        key_pwd_box.pack_start(key_pwd_show, False, False, 0)
        gen_grid.attach(key_pwd_box, 1, row, 2, 1)
        self.auth_rows['key_password'] = (key_pwd_lbl, key_pwd_box)
        row += 1

        # Username
        user_lbl = _field_label(_("Username:"))
        gen_grid.attach(user_lbl, 0, row, 1, 1)
        self.username_entry = Gtk.Entry()
        self.username_entry.set_hexpand(True)
        self.username_entry.set_text(self.cfg.get('username', ''))
        gen_grid.attach(self.username_entry, 1, row, 2, 1)
        self.auth_rows['username'] = (user_lbl, self.username_entry)
        row += 1

        # Password
        pwd_lbl = _field_label(_("Password:"))
        gen_grid.attach(pwd_lbl, 0, row, 1, 1)
        pwd_box = Gtk.HBox(spacing=6)
        self.password_entry = Gtk.Entry()
        self.password_entry.set_visibility(False)
        self.password_entry.set_hexpand(True)
        self.password_entry.set_placeholder_text(_("Leave blank to ask on connect"))
        self.password_entry.set_text(self.cfg.get('password', ''))
        pwd_show = Gtk.CheckButton(label=_("Show"))
        pwd_show.connect(
            "toggled",
            lambda w: self.password_entry.set_visibility(w.get_active())
        )
        pwd_box.pack_start(self.password_entry, True, True, 0)
        pwd_box.pack_start(pwd_show, False, False, 0)
        gen_grid.attach(pwd_box, 1, row, 2, 1)
        self.auth_rows['password'] = (pwd_lbl, pwd_box)
        row += 1

        # Static Key
        self.auth_rows['secret'] = self._cert_picker_row(
            gen_grid, row, _("Static Key:"), 'secret_path', 'secret_inline',
            ("*.key", "*.pem", "*.txt"),
        )

        notebook.append_page(gen_grid, Gtk.Label(label=_("VPN")))

        # --- Tab 2: IPv4 Settings (Static IPv4, DNS, Static Routes) ---
        ipv4_box = self._build_ipv4_tab()
        notebook.append_page(ipv4_box, Gtk.Label(label=_("IPv4 Settings")))

        # --- Tab 3: IPv6 Settings (Static IPv6, Static Routes) ---
        ipv6_box = self._build_ipv6_tab()
        notebook.append_page(ipv6_box, Gtk.Label(label=_("IPv6 Settings")))

        # --- Tab 4: Advanced / Tunnel ---
        tun_grid = Gtk.Grid()
        tun_grid.set_border_width(12)
        tun_grid.set_column_spacing(10)
        tun_grid.set_row_spacing(8)
        t_row = 0

        port_lbl = _field_label(_("Gateway Port:"))
        tun_grid.attach(port_lbl, 0, t_row, 1, 1)
        self.port_entry = Gtk.Entry()
        self.port_entry.set_text(str(self.cfg.get('port', '1194')))
        tun_grid.attach(self.port_entry, 1, t_row, 1, 1)
        t_row += 1

        proto_lbl = _field_label(_("Protocol:"))
        tun_grid.attach(proto_lbl, 0, t_row, 1, 1)
        self.proto_combo = Gtk.ComboBoxText()
        self.proto_combo.append('udp', "UDP")
        self.proto_combo.append('tcp', "TCP")
        self.proto_combo.set_active_id(
            'tcp' if self.cfg.get('proto', 'udp').startswith('tcp') else 'udp'
        )
        tun_grid.attach(self.proto_combo, 1, t_row, 1, 1)
        t_row += 1

        dev_lbl = _field_label(_("Virtual Device:"))
        tun_grid.attach(dev_lbl, 0, t_row, 1, 1)
        self.dev_combo = Gtk.ComboBoxText()
        self.dev_combo.append('tun', _("TUN (Routed IP Tunnel)"))
        self.dev_combo.append('tap', _("TAP (Bridged Ethernet)"))
        dev_val = 'tap' if self.cfg.get('dev', 'tun').startswith('tap') else 'tun'
        self.dev_combo.set_active_id(dev_val)
        tun_grid.attach(self.dev_combo, 1, t_row, 2, 1)
        t_row += 1

        comp_lbl = _field_label(_("Compression:"))
        tun_grid.attach(comp_lbl, 0, t_row, 1, 1)
        self.compress_combo = Gtk.ComboBoxText()
        cur_comp = self.cfg.get('compress', '')
        comp_idx = 0
        for idx, (c_code, c_title) in enumerate(self.COMPRESS_TYPES):
            self.compress_combo.append(c_code, c_title)
            if c_code == cur_comp:
                comp_idx = idx
        self.compress_combo.set_active(comp_idx)
        tun_grid.attach(self.compress_combo, 1, t_row, 2, 1)
        t_row += 1

        mtu_lbl = _field_label(_("Tunnel MTU:"))
        tun_grid.attach(mtu_lbl, 0, t_row, 1, 1)
        self.mtu_entry = Gtk.Entry()
        self.mtu_entry.set_placeholder_text(_("Default (1500)"))
        self.mtu_entry.set_text(str(self.cfg.get('tun_mtu', '')))
        tun_grid.attach(self.mtu_entry, 1, t_row, 1, 1)
        t_row += 1

        self.mssfix_check = Gtk.CheckButton(
            label=_("Restrict TCP Maximum Segment Size (mssfix)")
        )
        self.mssfix_check.set_active(bool(self.cfg.get('mssfix')))
        tun_grid.attach(self.mssfix_check, 1, t_row, 2, 1)
        t_row += 1

        self.remote_random_check = Gtk.CheckButton(
            label=_("Randomize remote hosts (remote-random)")
        )
        self.remote_random_check.set_active(bool(self.cfg.get('remote_random')))
        tun_grid.attach(self.remote_random_check, 1, t_row, 2, 1)

        notebook.append_page(tun_grid, Gtk.Label(label=_("Advanced")))

        # --- Tab 5: Security & TLS ---
        sec_grid = Gtk.Grid()
        sec_grid.set_border_width(12)
        sec_grid.set_column_spacing(10)
        sec_grid.set_row_spacing(8)
        s_row = 0

        cipher_lbl = _field_label(_("Cipher:"))
        sec_grid.attach(cipher_lbl, 0, s_row, 1, 1)
        self.cipher_combo = Gtk.ComboBoxText.new_with_entry()
        for c_opt in CIPHER_OPTIONS:
            self.cipher_combo.append_text(c_opt)
        self.cipher_combo.get_child().set_text(self.cfg.get('cipher', ''))
        sec_grid.attach(self.cipher_combo, 1, s_row, 2, 1)
        s_row += 1

        dc_lbl = _field_label(_("Data Ciphers:"))
        sec_grid.attach(dc_lbl, 0, s_row, 1, 1)
        self.data_ciphers_entry = Gtk.Entry()
        self.data_ciphers_entry.set_placeholder_text("AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305")
        self.data_ciphers_entry.set_text(self.cfg.get('data_ciphers', ''))
        sec_grid.attach(self.data_ciphers_entry, 1, s_row, 2, 1)
        s_row += 1

        hmac_lbl = _field_label(_("HMAC Auth:"))
        sec_grid.attach(hmac_lbl, 0, s_row, 1, 1)
        self.auth_digest_combo = Gtk.ComboBoxText.new_with_entry()
        for a_opt in AUTH_DIGEST_OPTIONS:
            self.auth_digest_combo.append_text(a_opt)
        self.auth_digest_combo.get_child().set_text(self.cfg.get('auth', ''))
        sec_grid.attach(self.auth_digest_combo, 1, s_row, 2, 1)
        s_row += 1

        rcert_lbl = _field_label(_("Verify Peer Cert:"))
        sec_grid.attach(rcert_lbl, 0, s_row, 1, 1)
        self.remote_cert_combo = Gtk.ComboBoxText()
        self.remote_cert_combo.append('', _("None"))
        self.remote_cert_combo.append('server', _("Server (remote-cert-tls server)"))
        self.remote_cert_combo.append('client', _("Client (remote-cert-tls client)"))
        self.remote_cert_combo.set_active_id(self.cfg.get('remote_cert_tls', ''))
        sec_grid.attach(self.remote_cert_combo, 1, s_row, 2, 1)
        s_row += 1

        x509_lbl = _field_label(_("Verify X.509 Name:"))
        sec_grid.attach(x509_lbl, 0, s_row, 1, 1)
        self.verify_x509_entry = Gtk.Entry()
        self.verify_x509_entry.set_text(self.cfg.get('verify_x509_name', ''))
        sec_grid.attach(self.verify_x509_entry, 1, s_row, 2, 1)
        s_row += 1

        tls_min_lbl = _field_label(_("Min TLS Version:"))
        sec_grid.attach(tls_min_lbl, 0, s_row, 1, 1)
        self.tls_min_combo = Gtk.ComboBoxText()
        for ver in ('', '1.0', '1.1', '1.2', '1.3'):
            self.tls_min_combo.append(ver, ver if ver else _("Default"))
        self.tls_min_combo.set_active_id(self.cfg.get('tls_version_min', ''))
        sec_grid.attach(self.tls_min_combo, 1, s_row, 1, 1)
        s_row += 1

        tls_mode_lbl = _field_label(_("TLS Auth Mode:"))
        sec_grid.attach(tls_mode_lbl, 0, s_row, 1, 1)
        self.tls_mode_combo = Gtk.ComboBoxText()
        for m_code, m_title in self.TLS_MODES:
            self.tls_mode_combo.append(m_code, m_title)
        self.tls_mode_combo.set_active_id(self.cfg.get('tls_mode', 'none'))
        self.tls_mode_combo.connect("changed", lambda _c: self.refresh_dynamic_visibility())
        sec_grid.attach(self.tls_mode_combo, 1, s_row, 2, 1)
        s_row += 1

        tls_key_pair = self._cert_picker_row(
            sec_grid, s_row, _("TLS Key File:"), 'tls_key_path', 'tls_key_inline',
            ("*.key", "*.pem", "*.txt"),
        )
        s_row += 1

        kdir_lbl = _field_label(_("Key Direction:"))
        sec_grid.attach(kdir_lbl, 0, s_row, 1, 1)
        self.key_dir_combo = Gtk.ComboBoxText()
        self.key_dir_combo.append('', _("Default / None"))
        self.key_dir_combo.append('0', "0")
        self.key_dir_combo.append('1', "1")
        self.key_dir_combo.append('bidirectional', "bidirectional")
        self.key_dir_combo.set_active_id(self.cfg.get('key_direction', ''))
        sec_grid.attach(self.key_dir_combo, 1, s_row, 1, 1)
        self.tls_key_rows = (*tls_key_pair, kdir_lbl, self.key_dir_combo)

        notebook.append_page(sec_grid, Gtk.Label(label=_("Security & TLS")))

        # --- Tab 6: Proxies ---
        prx_grid = Gtk.Grid()
        prx_grid.set_border_width(12)
        prx_grid.set_column_spacing(10)
        prx_grid.set_row_spacing(8)
        p_row = 0

        ptype_lbl = _field_label(_("Proxy Type:"))
        prx_grid.attach(ptype_lbl, 0, p_row, 1, 1)
        self.proxy_type_combo = Gtk.ComboBoxText()
        self.proxy_type_combo.append('none', _("Not Required"))
        self.proxy_type_combo.append('http', "HTTP")
        self.proxy_type_combo.append('socks', "SOCKS")
        self.proxy_type_combo.set_active_id(self.cfg.get('proxy_type', 'none'))
        self.proxy_type_combo.connect("changed", lambda _c: self.refresh_dynamic_visibility())
        prx_grid.attach(self.proxy_type_combo, 1, p_row, 2, 1)
        p_row += 1

        psrv_lbl = _field_label(_("Proxy Server:"))
        prx_grid.attach(psrv_lbl, 0, p_row, 1, 1)
        self.proxy_srv_entry = Gtk.Entry()
        self.proxy_srv_entry.set_hexpand(True)
        self.proxy_srv_entry.set_text(self.cfg.get('proxy_server', ''))
        prx_grid.attach(self.proxy_srv_entry, 1, p_row, 2, 1)
        p_row += 1

        pprt_lbl = _field_label(_("Proxy Port:"))
        prx_grid.attach(pprt_lbl, 0, p_row, 1, 1)
        self.proxy_port_entry = Gtk.Entry()
        self.proxy_port_entry.set_text(str(self.cfg.get('proxy_port', '')))
        prx_grid.attach(self.proxy_port_entry, 1, p_row, 1, 1)
        p_row += 1

        pusr_lbl = _field_label(_("Proxy Username:"))
        prx_grid.attach(pusr_lbl, 0, p_row, 1, 1)
        self.proxy_user_entry = Gtk.Entry()
        self.proxy_user_entry.set_text(self.cfg.get('proxy_username', ''))
        prx_grid.attach(self.proxy_user_entry, 1, p_row, 2, 1)
        p_row += 1

        ppwd_lbl = _field_label(_("Proxy Password:"))
        prx_grid.attach(ppwd_lbl, 0, p_row, 1, 1)
        self.proxy_pwd_entry = Gtk.Entry()
        self.proxy_pwd_entry.set_visibility(False)
        self.proxy_pwd_entry.set_text(self.cfg.get('proxy_password', ''))
        prx_grid.attach(self.proxy_pwd_entry, 1, p_row, 2, 1)

        self.proxy_rows = (
            psrv_lbl, self.proxy_srv_entry,
            pprt_lbl, self.proxy_port_entry,
            pusr_lbl, self.proxy_user_entry,
            ppwd_lbl, self.proxy_pwd_entry,
        )

        notebook.append_page(prx_grid, Gtk.Label(label=_("Proxies")))

    def _build_ipv4_tab(self):
        """Build the IPv4 Settings tab with Manual/Auto IP, DNS, and Static Routes."""
        vbox = Gtk.VBox(spacing=8)
        vbox.set_border_width(12)

        top_grid = Gtk.Grid()
        top_grid.set_column_spacing(10)
        top_grid.set_row_spacing(6)
        vbox.pack_start(top_grid, False, False, 0)

        top_grid.attach(_field_label(_("IPv4 Method:")), 0, 0, 1, 1)
        self.ipv4_method_combo = Gtk.ComboBoxText()
        self.ipv4_method_combo.append('auto', _("Automatic (VPN)"))
        self.ipv4_method_combo.append('manual', _("Manual (Static IPv4)"))
        init_m4 = 'manual' if (
            self.cfg.get('ipv4_method') == 'manual' or self.cfg.get('ifconfig_local')
        ) else 'auto'
        self.ipv4_method_combo.set_active_id(init_m4)
        self.ipv4_method_combo.connect("changed", lambda _c: self.refresh_dynamic_visibility())
        top_grid.attach(self.ipv4_method_combo, 1, 0, 2, 1)

        # Manual IPv4 fields: Address, Netmask / Remote IP, Gateway
        addr_lbl = _field_label(_("IPv4 Address:"))
        top_grid.attach(addr_lbl, 0, 1, 1, 1)
        self.ifconfig_local_entry = Gtk.Entry()
        self.ifconfig_local_entry.set_placeholder_text("10.8.0.2")
        self.ifconfig_local_entry.set_text(self.cfg.get('ifconfig_local', ''))
        top_grid.attach(self.ifconfig_local_entry, 1, 1, 2, 1)

        mask_lbl = _field_label(_("Netmask / Peer IP:"))
        top_grid.attach(mask_lbl, 0, 2, 1, 1)
        self.ifconfig_remote_entry = Gtk.Entry()
        self.ifconfig_remote_entry.set_placeholder_text("255.255.255.0 or 10.8.0.1")
        self.ifconfig_remote_entry.set_text(self.cfg.get('ifconfig_remote', ''))
        top_grid.attach(self.ifconfig_remote_entry, 1, 2, 2, 1)

        rgw_lbl = _field_label(_("IPv4 Gateway:"))
        top_grid.attach(rgw_lbl, 0, 3, 1, 1)
        self.route_gw_entry = Gtk.Entry()
        self.route_gw_entry.set_placeholder_text(_("Optional (e.g. 10.8.0.1)"))
        self.route_gw_entry.set_text(self.cfg.get('route_gateway', ''))
        top_grid.attach(self.route_gw_entry, 1, 3, 2, 1)

        self.ipv4_manual_widgets = (
            addr_lbl, self.ifconfig_local_entry,
            mask_lbl, self.ifconfig_remote_entry,
            rgw_lbl, self.route_gw_entry,
        )

        # DNS & Search Domains
        dns_lbl = _field_label(_("DNS Servers:"))
        top_grid.attach(dns_lbl, 0, 4, 1, 1)
        self.dns_entry = Gtk.Entry()
        self.dns_entry.set_hexpand(True)
        self.dns_entry.set_placeholder_text("1.1.1.1, 8.8.8.8")
        self.dns_entry.set_text(', '.join(self.cfg.get('dns_servers', [])))
        top_grid.attach(self.dns_entry, 1, 4, 2, 1)

        dom_lbl = _field_label(_("Search Domains:"))
        top_grid.attach(dom_lbl, 0, 5, 1, 1)
        self.domains_entry = Gtk.Entry()
        self.domains_entry.set_hexpand(True)
        self.domains_entry.set_text(', '.join(self.cfg.get('search_domains', [])))
        top_grid.attach(self.domains_entry, 1, 5, 2, 1)

        # Static Routes section
        vbox.pack_start(_bold_label(_("Static Routes (IPv4)")), False, False, 2)

        self.ipv4_routes_store = Gtk.ListStore(str, str, str, str)
        for rt in self.cfg.get('routes', []):
            self.ipv4_routes_store.append([
                rt.get('network', ''),
                rt.get('netmask', '255.255.255.0'),
                rt.get('gateway', 'vpn_gateway'),
                rt.get('metric', ''),
            ])

        self.ipv4_routes_tree = Gtk.TreeView(model=self.ipv4_routes_store)
        r4_cols = [
            (_("Address / Network"), 0, 140),
            (_("Netmask / Prefix"), 1, 130),
            (_("Gateway"), 2, 120),
            (_("Metric"), 3, 70),
        ]
        for title, col_idx, width in r4_cols:
            renderer = Gtk.CellRendererText()
            renderer.set_property("editable", True)
            renderer.connect("edited", self._on_ipv4_route_cell_edited, col_idx)
            col = Gtk.TreeViewColumn(title, renderer, text=col_idx)
            col.set_min_width(width)
            col.set_resizable(True)
            self.ipv4_routes_tree.append_column(col)

        r4_scroll = Gtk.ScrolledWindow()
        r4_scroll.set_shadow_type(Gtk.ShadowType.IN)
        r4_scroll.set_size_request(-1, 110)
        r4_scroll.add(self.ipv4_routes_tree)
        vbox.pack_start(r4_scroll, True, True, 0)

        # Quick-add route bar
        r4_add_box = Gtk.HBox(spacing=4)
        self.r4_net_entry = Gtk.Entry()
        self.r4_net_entry.set_placeholder_text(_("Network (e.g. 192.168.10.0)"))
        self.r4_mask_entry = Gtk.Entry()
        self.r4_mask_entry.set_placeholder_text(_("Netmask (255.255.255.0 or 24)"))
        self.r4_gw_entry = Gtk.Entry()
        self.r4_gw_entry.set_placeholder_text(_("Gateway (vpn_gateway)"))
        self.r4_metric_entry = Gtk.Entry()
        self.r4_metric_entry.set_width_chars(6)
        self.r4_metric_entry.set_placeholder_text(_("Metric"))

        r4_add_btn = Gtk.Button(label=_("Add"))
        r4_add_btn.connect("clicked", self._on_add_ipv4_route)
        r4_del_btn = Gtk.Button(label=_("Remove"))
        r4_del_btn.connect("clicked", self._on_remove_ipv4_route)

        r4_add_box.pack_start(self.r4_net_entry, True, True, 0)
        r4_add_box.pack_start(self.r4_mask_entry, True, True, 0)
        r4_add_box.pack_start(self.r4_gw_entry, True, True, 0)
        r4_add_box.pack_start(self.r4_metric_entry, False, False, 0)
        r4_add_box.pack_start(r4_add_btn, False, False, 0)
        r4_add_box.pack_start(r4_del_btn, False, False, 0)
        vbox.pack_start(r4_add_box, False, False, 0)

        self.redirect_gw_check = Gtk.CheckButton(
            label=_("Route all traffic through VPN (redirect-gateway)")
        )
        self.redirect_gw_check.set_active(bool(self.cfg.get('redirect_gateway')))
        vbox.pack_start(self.redirect_gw_check, False, False, 0)

        self.route_nopull_check = Gtk.CheckButton(
            label=_("Ignore automatically obtained routes (route-nopull)")
        )
        self.route_nopull_check.set_active(bool(self.cfg.get('route_nopull')))
        vbox.pack_start(self.route_nopull_check, False, False, 0)

        return vbox

    def _on_ipv4_route_cell_edited(self, _renderer, path, new_text, col_idx):
        self.ipv4_routes_store[path][col_idx] = new_text.strip()

    def _on_add_ipv4_route(self, _widget):
        net = self.r4_net_entry.get_text().strip()
        if not net:
            return
        mask = self.r4_mask_entry.get_text().strip() or '255.255.255.0'
        gw = self.r4_gw_entry.get_text().strip() or 'vpn_gateway'
        metric = self.r4_metric_entry.get_text().strip()
        self.ipv4_routes_store.append([net, mask, gw, metric])
        self.r4_net_entry.set_text('')
        self.r4_mask_entry.set_text('')
        self.r4_gw_entry.set_text('')
        self.r4_metric_entry.set_text('')

    def _on_remove_ipv4_route(self, _widget):
        selection = self.ipv4_routes_tree.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter is not None:
            model.remove(tree_iter)

    def _build_ipv6_tab(self):
        """Build the IPv6 Settings tab with Manual/Auto/Disabled IPv6 and Static Routes."""
        vbox = Gtk.VBox(spacing=8)
        vbox.set_border_width(12)

        top_grid = Gtk.Grid()
        top_grid.set_column_spacing(10)
        top_grid.set_row_spacing(6)
        vbox.pack_start(top_grid, False, False, 0)

        top_grid.attach(_field_label(_("IPv6 Method:")), 0, 0, 1, 1)
        self.ipv6_method_combo = Gtk.ComboBoxText()
        self.ipv6_method_combo.append('auto', _("Automatic (VPN)"))
        self.ipv6_method_combo.append('manual', _("Manual (Static IPv6)"))
        self.ipv6_method_combo.append('disabled', _("Disabled / Ignore"))
        init_m6 = self.cfg.get('ipv6_method', 'auto')
        if init_m6 not in ('auto', 'manual', 'disabled'):
            init_m6 = 'auto'
        self.ipv6_method_combo.set_active_id(init_m6)
        self.ipv6_method_combo.connect("changed", lambda _c: self.refresh_dynamic_visibility())
        top_grid.attach(self.ipv6_method_combo, 1, 0, 2, 1)

        addr6_lbl = _field_label(_("IPv6 Address:"))
        top_grid.attach(addr6_lbl, 0, 1, 1, 1)
        self.ifconfig_ipv6_local_entry = Gtk.Entry()
        self.ifconfig_ipv6_local_entry.set_hexpand(True)
        self.ifconfig_ipv6_local_entry.set_placeholder_text("fd00::2")
        self.ifconfig_ipv6_local_entry.set_text(self.cfg.get('ifconfig_ipv6_local', ''))
        top_grid.attach(self.ifconfig_ipv6_local_entry, 1, 1, 2, 1)

        plen6_lbl = _field_label(_("Prefix Length:"))
        top_grid.attach(plen6_lbl, 0, 2, 1, 1)
        self.ifconfig_ipv6_prefix_entry = Gtk.Entry()
        self.ifconfig_ipv6_prefix_entry.set_placeholder_text("64")
        self.ifconfig_ipv6_prefix_entry.set_text(str(self.cfg.get('ifconfig_ipv6_prefix', '64')))
        top_grid.attach(self.ifconfig_ipv6_prefix_entry, 1, 2, 1, 1)

        gw6_lbl = _field_label(_("IPv6 Gateway / Peer:"))
        top_grid.attach(gw6_lbl, 0, 3, 1, 1)
        self.ifconfig_ipv6_remote_entry = Gtk.Entry()
        self.ifconfig_ipv6_remote_entry.set_placeholder_text("fd00::1")
        self.ifconfig_ipv6_remote_entry.set_text(self.cfg.get('ifconfig_ipv6_remote', ''))
        top_grid.attach(self.ifconfig_ipv6_remote_entry, 1, 3, 2, 1)

        self.ipv6_manual_widgets = (
            addr6_lbl, self.ifconfig_ipv6_local_entry,
            plen6_lbl, self.ifconfig_ipv6_prefix_entry,
            gw6_lbl, self.ifconfig_ipv6_remote_entry,
        )

        # Static Routes (IPv6)
        vbox.pack_start(_bold_label(_("Static Routes (IPv6)")), False, False, 2)

        self.ipv6_routes_store = Gtk.ListStore(str, str, str)
        for rt6 in self.cfg.get('routes_ipv6', []):
            self.ipv6_routes_store.append([
                rt6.get('network', ''),
                rt6.get('gateway', ''),
                rt6.get('metric', ''),
            ])

        self.ipv6_routes_tree = Gtk.TreeView(model=self.ipv6_routes_store)
        r6_cols = [
            (_("Destination (CIDR)"), 0, 200),
            (_("Gateway"), 1, 160),
            (_("Metric"), 2, 80),
        ]
        for title, col_idx, width in r6_cols:
            renderer = Gtk.CellRendererText()
            renderer.set_property("editable", True)
            renderer.connect("edited", self._on_ipv6_route_cell_edited, col_idx)
            col = Gtk.TreeViewColumn(title, renderer, text=col_idx)
            col.set_min_width(width)
            col.set_resizable(True)
            self.ipv6_routes_tree.append_column(col)

        r6_scroll = Gtk.ScrolledWindow()
        r6_scroll.set_shadow_type(Gtk.ShadowType.IN)
        r6_scroll.set_size_request(-1, 110)
        r6_scroll.add(self.ipv6_routes_tree)
        vbox.pack_start(r6_scroll, True, True, 0)

        r6_add_box = Gtk.HBox(spacing=4)
        self.r6_net_entry = Gtk.Entry()
        self.r6_net_entry.set_placeholder_text(_("Network (e.g. fd00:10::/64)"))
        self.r6_gw_entry = Gtk.Entry()
        self.r6_gw_entry.set_placeholder_text(_("Gateway (optional)"))
        self.r6_metric_entry = Gtk.Entry()
        self.r6_metric_entry.set_width_chars(6)
        self.r6_metric_entry.set_placeholder_text(_("Metric"))

        r6_add_btn = Gtk.Button(label=_("Add"))
        r6_add_btn.connect("clicked", self._on_add_ipv6_route)
        r6_del_btn = Gtk.Button(label=_("Remove"))
        r6_del_btn.connect("clicked", self._on_remove_ipv6_route)

        r6_add_box.pack_start(self.r6_net_entry, True, True, 0)
        r6_add_box.pack_start(self.r6_gw_entry, True, True, 0)
        r6_add_box.pack_start(self.r6_metric_entry, False, False, 0)
        r6_add_box.pack_start(r6_add_btn, False, False, 0)
        r6_add_box.pack_start(r6_del_btn, False, False, 0)
        vbox.pack_start(r6_add_box, False, False, 0)

        return vbox

    def _on_ipv6_route_cell_edited(self, _renderer, path, new_text, col_idx):
        self.ipv6_routes_store[path][col_idx] = new_text.strip()

    def _on_add_ipv6_route(self, _widget):
        net6 = self.r6_net_entry.get_text().strip()
        if not net6:
            return
        gw6 = self.r6_gw_entry.get_text().strip()
        metric6 = self.r6_metric_entry.get_text().strip()
        self.ipv6_routes_store.append([net6, gw6, metric6])
        self.r6_net_entry.set_text('')
        self.r6_gw_entry.set_text('')
        self.r6_metric_entry.set_text('')

    def _on_remove_ipv6_route(self, _widget):
        selection = self.ipv6_routes_tree.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter is not None:
            model.remove(tree_iter)

    def _build_wireguard_notebook(self, main_box):
        """Build the WireGuard configuration tabs."""
        notebook = Gtk.Notebook()
        main_box.pack_start(notebook, True, True, 0)

        grid = Gtk.Grid()
        grid.set_border_width(12)
        grid.set_column_spacing(10)
        grid.set_row_spacing(8)
        row = 0

        grid.attach(_bold_label(_("Interface")), 0, row, 3, 1)
        row += 1

        grid.attach(_field_label(_("Tunnel Name:")), 0, row, 1, 1)
        self.wg_id_entry = Gtk.Entry()
        self.wg_id_entry.set_text(self.cfg.get('profile_id', 'wg0'))
        self.wg_id_entry.connect("changed", self._on_wg_id_edited)
        grid.attach(self.wg_id_entry, 1, row, 2, 1)
        row += 1

        grid.attach(_field_label(_("IPv4 / IPv6 Addresses:")), 0, row, 1, 1)
        self.wg_addr_entry = Gtk.Entry()
        self.wg_addr_entry.set_hexpand(True)
        self.wg_addr_entry.set_placeholder_text("10.0.0.2/32, fd00::2/64")
        self.wg_addr_entry.set_text(self.cfg.get('address', ''))
        grid.attach(self.wg_addr_entry, 1, row, 2, 1)
        row += 1

        grid.attach(_field_label(_("Private Key:")), 0, row, 1, 1)
        priv_box = Gtk.HBox(spacing=6)
        self.wg_priv_entry = Gtk.Entry()
        self.wg_priv_entry.set_visibility(False)
        self.wg_priv_entry.set_hexpand(True)
        self.wg_priv_entry.set_text(self.cfg.get('private_key', ''))
        priv_show = Gtk.CheckButton(label=_("Show"))
        priv_show.connect("toggled", lambda w: self.wg_priv_entry.set_visibility(w.get_active()))
        priv_box.pack_start(self.wg_priv_entry, True, True, 0)
        priv_box.pack_start(priv_show, False, False, 0)
        grid.attach(priv_box, 1, row, 2, 1)
        row += 1

        grid.attach(_field_label(_("DNS Servers:")), 0, row, 1, 1)
        self.wg_dns_entry = Gtk.Entry()
        self.wg_dns_entry.set_text(self.cfg.get('dns', ''))
        grid.attach(self.wg_dns_entry, 1, row, 2, 1)
        row += 1

        grid.attach(_field_label(_("MTU:")), 0, row, 1, 1)
        self.wg_mtu_entry = Gtk.Entry()
        self.wg_mtu_entry.set_text(self.cfg.get('mtu', ''))
        grid.attach(self.wg_mtu_entry, 1, row, 1, 1)
        row += 1

        grid.attach(_bold_label(_("Peer & Routed Networks")), 0, row, 3, 1)
        row += 1

        grid.attach(_field_label(_("Public Key:")), 0, row, 1, 1)
        self.wg_pub_entry = Gtk.Entry()
        self.wg_pub_entry.set_hexpand(True)
        self.wg_pub_entry.set_text(self.cfg.get('public_key', ''))
        grid.attach(self.wg_pub_entry, 1, row, 2, 1)
        row += 1

        grid.attach(_field_label(_("Preshared Key:")), 0, row, 1, 1)
        psk_box = Gtk.HBox(spacing=6)
        self.wg_psk_entry = Gtk.Entry()
        self.wg_psk_entry.set_visibility(False)
        self.wg_psk_entry.set_hexpand(True)
        self.wg_psk_entry.set_text(self.cfg.get('preshared_key', ''))
        psk_show = Gtk.CheckButton(label=_("Show"))
        psk_show.connect("toggled", lambda w: self.wg_psk_entry.set_visibility(w.get_active()))
        psk_box.pack_start(self.wg_psk_entry, True, True, 0)
        psk_box.pack_start(psk_show, False, False, 0)
        grid.attach(psk_box, 1, row, 2, 1)
        row += 1

        grid.attach(_field_label(_("Endpoint:")), 0, row, 1, 1)
        self.wg_endpoint_entry = Gtk.Entry()
        self.wg_endpoint_entry.set_placeholder_text("vpn.example.com:51820")
        self.wg_endpoint_entry.set_text(self.cfg.get('endpoint', ''))
        grid.attach(self.wg_endpoint_entry, 1, row, 2, 1)
        row += 1

        grid.attach(_field_label(_("Allowed IPs (Routes):")), 0, row, 1, 1)
        self.wg_allowed_entry = Gtk.Entry()
        self.wg_allowed_entry.set_text(self.cfg.get('allowed_ips', '0.0.0.0/0, ::/0'))
        grid.attach(self.wg_allowed_entry, 1, row, 2, 1)
        row += 1

        grid.attach(_field_label(_("Persistent Keepalive:")), 0, row, 1, 1)
        self.wg_keepalive_entry = Gtk.Entry()
        self.wg_keepalive_entry.set_text(self.cfg.get('persistent_keepalive', ''))
        grid.attach(self.wg_keepalive_entry, 1, row, 1, 1)

        notebook.append_page(grid, Gtk.Label(label="WireGuard"))

    def refresh_dynamic_visibility(self):
        """Show only the fields relevant to the selected authentication/IP/TLS/proxy mode."""
        if self.vpn_type == 'wireguard':
            return
        auth_type = self.auth_type_combo.get_active_id() or 'tls'
        visibility = {
            'ca': auth_type in ('tls', 'password', 'tls-password'),
            'cert': auth_type in ('tls', 'tls-password'),
            'key': auth_type in ('tls', 'tls-password'),
            'key_password': auth_type in ('tls', 'tls-password'),
            'username': auth_type in ('password', 'tls-password'),
            'password': auth_type in ('password', 'tls-password'),
            'secret': auth_type == 'static-key',
        }
        for key, visible in visibility.items():
            for widget in self.auth_rows.get(key, ()):
                widget.set_visible(visible)

        ipv4_manual = (self.ipv4_method_combo.get_active_id() == 'manual') or (
            auth_type == 'static-key'
        )
        for widget in getattr(self, 'ipv4_manual_widgets', ()):
            widget.set_sensitive(ipv4_manual)

        ipv6_mode = self.ipv6_method_combo.get_active_id() or 'auto'
        ipv6_manual = ipv6_mode == 'manual'
        for widget in getattr(self, 'ipv6_manual_widgets', ()):
            widget.set_sensitive(ipv6_manual)

        tls_mode = self.tls_mode_combo.get_active_id() or 'none'
        tls_visible = tls_mode != 'none'
        for widget in self.tls_key_rows:
            widget.set_visible(tls_visible)

        proxy_type = self.proxy_type_combo.get_active_id() or 'none'
        proxy_visible = proxy_type != 'none'
        for widget in self.proxy_rows:
            widget.set_visible(proxy_visible)

    def on_save_clicked(self, _widget):
        """Collect form entries, validate, and save the VPN configuration."""
        self.cfg['name'] = self.name_entry.get_text().strip()

        try:
            if self.vpn_type == 'wireguard':
                self.cfg['profile_id'] = self.wg_id_entry.get_text().strip()
                self.cfg['address'] = self.wg_addr_entry.get_text().strip()
                self.cfg['private_key'] = self.wg_priv_entry.get_text().strip()
                self.cfg['dns'] = self.wg_dns_entry.get_text().strip()
                self.cfg['mtu'] = self.wg_mtu_entry.get_text().strip()
                self.cfg['public_key'] = self.wg_pub_entry.get_text().strip()
                self.cfg['preshared_key'] = self.wg_psk_entry.get_text().strip()
                self.cfg['endpoint'] = self.wg_endpoint_entry.get_text().strip()
                self.cfg['allowed_ips'] = self.wg_allowed_entry.get_text().strip()
                self.cfg['persistent_keepalive'] = self.wg_keepalive_entry.get_text().strip()
                saved_id = save_wireguard_config(self.cfg)
            else:
                # Commit any typed but un-added route from the quick-add bar
                if self.r4_net_entry.get_text().strip():
                    self._on_add_ipv4_route(None)
                if self.r6_net_entry.get_text().strip():
                    self._on_add_ipv6_route(None)

                self.cfg['gateway'] = self.gateway_entry.get_text().strip()
                self.cfg['auth_type'] = self.auth_type_combo.get_active_id() or 'tls'
                self.cfg['auth_user_pass'] = self.cfg['auth_type'] in (
                    'password', 'tls-password'
                )
                self.cfg['key_password'] = self.key_pwd_entry.get_text()
                self.cfg['username'] = self.username_entry.get_text().strip()
                self.cfg['password'] = self.password_entry.get_text()

                self.cfg['ipv4_method'] = self.ipv4_method_combo.get_active_id() or 'auto'
                self.cfg['ifconfig_local'] = self.ifconfig_local_entry.get_text().strip()
                self.cfg['ifconfig_remote'] = self.ifconfig_remote_entry.get_text().strip()
                self.cfg['route_gateway'] = self.route_gw_entry.get_text().strip()
                self.cfg['routes'] = [
                    {
                        'network': row[0].strip(),
                        'netmask': row[1].strip() or '255.255.255.0',
                        'gateway': row[2].strip() or 'vpn_gateway',
                        'metric': row[3].strip(),
                    }
                    for row in self.ipv4_routes_store
                    if row[0].strip()
                ]

                self.cfg['ipv6_method'] = self.ipv6_method_combo.get_active_id() or 'auto'
                self.cfg['ifconfig_ipv6_local'] = self.ifconfig_ipv6_local_entry.get_text().strip()
                self.cfg['ifconfig_ipv6_prefix'] = (
                    self.ifconfig_ipv6_prefix_entry.get_text().strip() or '64'
                )
                self.cfg['ifconfig_ipv6_remote'] = (
                    self.ifconfig_ipv6_remote_entry.get_text().strip()
                )
                self.cfg['routes_ipv6'] = [
                    {
                        'network': row[0].strip(),
                        'gateway': row[1].strip(),
                        'metric': row[2].strip(),
                    }
                    for row in self.ipv6_routes_store
                    if row[0].strip()
                ]

                self.cfg['port'] = self.port_entry.get_text().strip() or '1194'
                self.cfg['proto'] = self.proto_combo.get_active_id() or 'udp'
                self.cfg['dev'] = self.dev_combo.get_active_id() or 'tun'
                self.cfg['compress'] = self.compress_combo.get_active_id() or ''
                self.cfg['tun_mtu'] = self.mtu_entry.get_text().strip()
                self.cfg['mssfix'] = 'yes' if self.mssfix_check.get_active() else ''
                self.cfg['redirect_gateway'] = self.redirect_gw_check.get_active()
                self.cfg['route_nopull'] = self.route_nopull_check.get_active()
                self.cfg['remote_random'] = self.remote_random_check.get_active()

                self.cfg['cipher'] = self.cipher_combo.get_child().get_text().strip()
                self.cfg['data_ciphers'] = self.data_ciphers_entry.get_text().strip()
                self.cfg['auth'] = self.auth_digest_combo.get_child().get_text().strip()
                self.cfg['remote_cert_tls'] = self.remote_cert_combo.get_active_id() or ''
                self.cfg['verify_x509_name'] = self.verify_x509_entry.get_text().strip()
                self.cfg['tls_version_min'] = self.tls_min_combo.get_active_id() or ''
                self.cfg['tls_mode'] = self.tls_mode_combo.get_active_id() or 'none'
                self.cfg['key_direction'] = self.key_dir_combo.get_active_id() or ''

                self.cfg['dns_servers'] = [
                    d.strip() for d in self.dns_entry.get_text().split(',') if d.strip()
                ]
                self.cfg['search_domains'] = [
                    d.strip() for d in self.domains_entry.get_text().split(',') if d.strip()
                ]
                self.cfg['proxy_type'] = self.proxy_type_combo.get_active_id() or 'none'
                self.cfg['proxy_server'] = self.proxy_srv_entry.get_text().strip()
                self.cfg['proxy_port'] = self.proxy_port_entry.get_text().strip()
                self.cfg['proxy_username'] = self.proxy_user_entry.get_text().strip()
                self.cfg['proxy_password'] = self.proxy_pwd_entry.get_text()

                saved_id = save_openvpn_config(self.cfg)
        except ValueError as err:
            _show_error_dialog(self, _("Invalid VPN configuration"), str(err))
            return

        self.destroy()
        if self.on_saved is not None:
            self.on_saved(saved_id, self.vpn_type)


class OpenVPNAuthDialog(Gtk.Window):
    """Prompt for OpenVPN username and password before connecting."""

    def __init__(self, profile_id, display_name, initial_user='', on_submit=None):
        super().__init__(title=_("VPN Authentication Required"))
        self.set_border_width(12)
        self.set_default_size(420, 200)
        self.profile_id = profile_id
        self.on_submit = on_submit

        vbox = Gtk.VBox(spacing=10)
        self.add(vbox)

        heading = _bold_label(_("Authentication required for VPN %s") % display_name)
        vbox.pack_start(heading, False, False, 4)

        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(8)
        vbox.pack_start(grid, True, True, 0)

        grid.attach(_field_label(_("Username:")), 0, 0, 1, 1)
        self.user_entry = Gtk.Entry()
        self.user_entry.set_hexpand(True)
        self.user_entry.set_text(initial_user or '')
        grid.attach(self.user_entry, 1, 0, 2, 1)

        grid.attach(_field_label(_("Password:")), 0, 1, 1, 1)
        self.pwd_entry = Gtk.Entry()
        self.pwd_entry.set_visibility(False)
        self.pwd_entry.set_hexpand(True)
        grid.attach(self.pwd_entry, 1, 1, 2, 1)

        show_chk = Gtk.CheckButton(label=_("Show password"))
        show_chk.connect("toggled", lambda w: self.pwd_entry.set_visibility(w.get_active()))
        grid.attach(show_chk, 1, 2, 2, 1)

        btn_box = Gtk.HBox(spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        vbox.pack_end(btn_box, False, False, 0)

        cancel_btn = Gtk.Button(stock=Gtk.STOCK_CANCEL)
        cancel_btn.connect("clicked", lambda _w: self.destroy())
        btn_box.pack_start(cancel_btn, False, False, 0)

        connect_btn = Gtk.Button(stock=Gtk.STOCK_CONNECT)
        connect_btn.connect("clicked", self._on_connect)
        btn_box.pack_start(connect_btn, False, False, 0)

    def _on_connect(self, _widget):
        username = self.user_entry.get_text().strip()
        password = self.pwd_entry.get_text()
        self.destroy()
        if self.on_submit is not None:
            self.on_submit(self.profile_id, username, password)
