NetworkMgr
==========
NetworkMgr is a Python GTK3 network manager for FreeBSD, GhostBSD, TrueOS and DragonFlyBSD. NetworkMgr support both netif and OpenRC network.

![alt text](https://image.ibb.co/bWha3R/Screenshot_at_2017_11_24_20_57_33.png)

Installation
============

Packages to be installed before NetworkMgr.

`pkg install py36-setuptools py36-gobject3 doas gtk-update-icon-cache hicolor-icon-theme`

Download NetworkMgr or clone it:

`git clone https://github.com/GhostBSD/networkmgr.git`
  
To install NetworkMgr:

`cd networkmgr`

If NetworkMgr installed by package deinstall networkmrg first before installing with setup.py

`pkg delete networkmgr`

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
