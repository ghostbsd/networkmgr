# NetworkMgr

A network manager based on Python and GTK3 for FreeBSD, GhostBSD, and DragonFlyBSD. 

NetworkMgr supports FreeBSD rc(8) and openrc(8). 

## Installation

### On FreeBSD

See https://www.freshports.org/net-mgmt/networkmgr/#add for instructions on installing NetworkMgr.

#### Install using Python

Packages that have to be installed before installing NetworkMgr:

`pkg install sudo py311-setuptools py311-gobject3 gtk-update-icon-cache hicolor-icon-theme`

If NetworkMgr was previously installed using a package, remove it:  

`pkg delete networkmgr`

Download NetworkMgr, or clone this repository:

`git clone https://github.com/GhostBSD/networkmgr.git`

Then: 

`cd networkmgr` and `python3.8 setup.py install`

Users of NetworkMgr must be members of the _wheel_ group. To add a user: 

`pw groupmod wheel -m username`

## VPN Support & Required Packages

NetworkMgr supports importing, creating, editing, and managing **OpenVPN**, **WireGuard**, **IPsec (IKEv2 / IKEv1)**, and **L2TP/IPsec (Windows Server / Corporate VPN)** connections directly from the system tray and configuration window.

To install all VPN backends at once on GhostBSD / FreeBSD:

```shell
sudo pkg install openvpn wireguard-tools strongswan mpd5
```

Or install only the packages needed for your specific VPN protocol:

| VPN Protocol | Required Packages | Install Command |
| :--- | :--- | :--- |
| **OpenVPN** (`.ovpn`, `.conf`) | `security/openvpn` | `sudo pkg install openvpn` |
| **WireGuard** (`.conf`) | `net/wireguard-tools` | `sudo pkg install wireguard-tools` |
| **IPsec — IKEv2 / IKEv1** (EAP-MSCHAPv2 / Windows Server IKEv2, PSK, X.509, XAuth) | `security/strongswan` | `sudo pkg install strongswan` |
| **L2TP / IPsec** (Windows Server L2TP, MikroTik, Ubiquiti, FortiGate) | `security/strongswan`, `net/mpd5` | `sudo pkg install strongswan mpd5` |

## Starting NetworkMgr

If the desktop environment supports XDG then you can simply log out, or restart the computer. NetworkMgr should start automatically at login time.

## Managing Translations
To create a translation file.
```shell
./setup.py create_translation --locale=fr
```
To update all translation files
```shell
./setup.py update_translations
```
