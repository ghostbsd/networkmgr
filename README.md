NetworkMGR
==========

Networkmgr is build with Python GTK and it is a network manager for FreeBSD and GhostBSD.

Installation
============

To Install NetworkMGR Pygtk and doas need to be install.

`pkg install py27-gtk2 doas`
  
Once Pygtk and doas are installed you can install NetworkMGR.

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


when rebooting it should automaticaly start is the desktop support xdg and make sure that the user using NetworkMGR is in the operator group.




