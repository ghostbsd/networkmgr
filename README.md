## NetworkMgr

A Python GTK3 network manager for FreeBSD, GhostBSD, and DragonFlyBSD. 

![alt text](https://image.ibb.co/bWha3R/Screenshot_at_2017_11_24_20_57_33.png)

NetworkMgr supports FreeBSD rc(8) and openrc(8) supported. 

### Installation

#### On FreeBSD

See https://www.freshports.org/net-mgmt/networkmgr/#add

#### Install using Python

Packages to be installed before NetworkMgr:

`pkg install sudo py38-setuptools py38-gobject3 gtk-update-icon-cache hicolor-icon-theme`

If NetworkMgr was previously installed using a package, remove it:  

`pkg delete networkmgr`

Download NetworkMgr, or clone this repository:

`git clone https://github.com/GhostBSD/networkmgr.git`

Then: 

`cd networkmgr`

`python3.8 setup.py install`

Users of NetworkMgr must be members of the _wheel_ group. To add a user: 

`pw groupmod wheel -m username`

### Starting 

If the desktop environment supports XDG: log out, or restart the computer. NetworkMgr should start automatically at login time.

### For Development dicussion 

You can join us at [#networkmgr](irc://irc.libera.chat:6697/networkmgr) on irc.libera.chat:6697
