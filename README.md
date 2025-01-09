# NetworkMgr

A network manager based on Python and GTK3 for FreeBSD, GhostBSD, and DragonFlyBSD. 

![alt text](https://image.ibb.co/bWha3R/Screenshot_at_2017_11_24_20_57_33.png)

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

## Starting NetworkMgr

If the desktop environment supports XDG then you can simply log out, or restart the computer. NetworkMgr should start automatically at login time.

## Managing Translations
To create a translation file.
```shell
./setup.py create_translation --locale=fr
```

## For Development discussion 

You can join us at [#networkmgr](irc://irc.libera.chat:6697/networkmgr) on irc.libera.chat:6697
