#!/usr/local/bin/python

import os
#import sys
import shutil

share = "/usr/local/share/networkmgr"


class InstallAndUpdateDataDirectory():

    def __init__(self):
        if not os.path.exists(share):
            shutil.copytree("networkmgr", share)
        else:
            shutil.rmtree(share)
            shutil.copytree("networkmgr", share)
        shutil.copy("networkmgr.sh", "/usr/local/bin/networkmgr")
        shutil.copy("netcardmgr.py", "/usr/local/bin/netcardmgr")
        shutil.copy("networkmgr.desktop", "/usr/local/etc/xdg/autostart/networkmgr.desktop")
InstallAndUpdateDataDirectory()