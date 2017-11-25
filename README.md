NetworkMgr
==========

NetworkMgr is a network manager for FreeBSD and GhostBSD built with Python GTK.

Installation
============

Packages to be installed before NetworkMgr.

`pkg install py36-setuptools py36-gobject3 doas gtk-update-icon-cache hicolor-icon-theme`

Download NetworkMgr or clone it:

`git clone https://github.com/GhostBSD/networkmgr.git`
  
To install NetworkMgr:

`cd networkmgr`

`python3.6 setup.py install`

Make sure that /usr/local/etc/doas.conf exists.  If not, create it.

`touch /usr/local/etc/doas.conf`

Make sure that doas.conf has something similar to this:
```
permit nopass keepenv root
permit :wheel
permit nopass keepenv :wheel cmd netcardmgr
permit nopass keepenv :wheel cmd ifconfig
permit nopass keepenv :wheel cmd service

```
When rebooting NetworkMgr should automatically start if the desktop supports xdg.  Make sure that the user using NetworkMgr is in the wheel group.
