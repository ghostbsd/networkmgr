NetworkMgr
==========

NetworkMgr is build with Python GTK and it is a network manager for FreeBSD and GhostBSD.

Installation
============

To Install NetworkMgr Pygtk and doas need to be install.

`pkg install py27-gtk2 doas`

Download NetworkMgr or clone it:

`git clone https://github.com/GhostBSD/networkmgr.git`
  
 To install NetworkMgr:

`cd networkmgr`

`python setup.py install`

Make sure that /usr/local/etc/doas.conf exit if not create it.

`touch /usr/local/etc/doas.conf`

Make sure that the doas conf have someting simular like this:
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
When rebooting it should automaticaly start is the desktop support xdg and make sure that the user using NetworkMgr is in the wheel group.





