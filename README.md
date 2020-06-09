NetworkMgr
==========
NetworkMgr is a Python GTK3 network manager for FreeBSD, GhostBSD, TrueOS and DragonFlyBSD. NetworkMgr support both netif and OpenRC network.

![alt text](https://image.ibb.co/bWha3R/Screenshot_at_2017_11_24_20_57_33.png)

Installation
============

Packages to be installed before NetworkMgr.

`pkg install sudo py37-setuptools py37-gobject3 gtk-update-icon-cache hicolor-icon-theme`

Download NetworkMgr or clone it:

`git clone https://github.com/GhostBSD/networkmgr.git`
  
To install NetworkMgr:

`cd networkmgr`

If NetworkMgr installed by package deinstall networkmrg first before installing with setup.py

`pkg delete networkmgr`

`python3.7 setup.py install`

When rebooting NetworkMgr should automatically start if the desktop supports xdg.  Make sure that the user using NetworkMgr is in the wheel group.
