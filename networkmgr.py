#!/usr/local/bin/python

from subprocess import call
from sys import path
from trayicon import trayIcon

path.append("/usr/local/share/networkmgr")

call("sudo operator python /usr/local/share/networkmgr/netcardmgr.py",
     shell=True)

i = trayIcon()
i.tray()
