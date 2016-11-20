NetworkMGR
==========
Networkmgr is build with Python GTK and it is a network manager for FreeBSD and GhostBSD.

Installation
============
Operator need to be install in order to have NetworkMGR to work.
(https://github.com/GhostBSD/operator)

To Install NetworkMGR Pygtk need to be install.
'pkg install py27-gtk2'
  
Once Pygtk and Operator are installed you can install NetworkMGR.
  python setup.py install
when rebooting it should automaticaly start is the desktop support xdg and make sure that the user using NetworkMGR is in the operator group.




