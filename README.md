NetworkMgr
==========

NetworkMgr is a network manager for FreeBSD and GhostBSD built with Python GTK.

Installation
============

PyGtk and doas need to be installed before NetworkMgr.

`pkg install py27-gtk2 doas`

Download NetworkMgr or clone it:

`git clone https://github.com/GhostBSD/networkmgr.git`
  
To install NetworkMgr:

`cd networkmgr`

`python setup.py install`

Make sure that /usr/local/etc/doas.conf exists.  If not, create it.

`touch /usr/local/etc/doas.conf`

Make sure that doas.conf has something similar to this:
```
permit :wheel
permit nopass keepenv :wheel cmd netcardmgr
permit nopass keepenv :wheel cmd detect-nics
permit nopass keepenv :wheel cmd detect-wifi
permit nopass keepenv :wheel cmd ifconfig
permit nopass keepenv :wheel cmd service
permit nopass keepenv :wheel cmd wpa_supplicant
permit nopass keepenv root
```
When rebooting NetworkMgr should automaticaly start if the desktop supports xdg.  Make sure that the user using NetworkMgr is in the wheel group.
