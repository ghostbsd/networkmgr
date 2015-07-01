#!/usr/local/bin/python

from subprocess import call
from sys import path
path.append("/usr/local/share/networkmgr")
from trayicon import trayIcon


call("sudo operator python /usr/local/share/networkmgr/netcardmgr.py",
     shell=True)

i = trayIcon()
i.tray()
