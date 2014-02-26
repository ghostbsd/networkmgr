#!/usr/local/bin/python

import os
import shutil

share = "/usr/local/share/networkmgr"
sudoers = "/usr/local/etc/sudoers"
sudoline = '%wheel ALL=(ALL) NOPASSWD: /usr/local/share/networkmgr/trayicon.py'
sudo = "# %wheel ALL=(ALL) NOPASSWD: ALL"
deskfile = "/usr/local/etc/xdg/autostart/networkmgr.desktop"


class InstallAndUpdateDataDirectory():

    def __init__(self):
        if not os.path.exists(share):
            shutil.copytree("networkmgr", share)
        else:
            shutil.rmtree(share)
            shutil.copytree("networkmgr", share)
        shutil.copy("networkmgr.sh", "/usr/local/bin/networkmgr")
        shutil.copy("networkmgr.desktop", deskfile)
        if not sudoline in open(sudoers).read():
            with open(sudoers, "r") as sources:
                lines = sources.readlines()
            with open(sudoers, "w") as sources:
                for line in lines:
                    sources.write(line.replace('# %wheel ALL=(ALL) NOPASSWD: ALL', '%wheel ALL=(ALL) NOPASSWD: /usr/local/share/networkmgr/trayicon.py'))

if os.path.exists(sudoers):
    InstallAndUpdateDataDirectory()
else:
    print('Sudo is missing please install sudo')