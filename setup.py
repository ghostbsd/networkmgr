#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from platform import system
from setuptools import setup
from subprocess import run, Popen, PIPE

__VERSION__ = '4.6'
PROGRAM_VERSION = __VERSION__

prefix = '/usr/local' if system() == 'FreeBSD' else sys.prefix

cmd = ["kenv", "rc_system"]
rc_system = Popen(cmd, stdout=PIPE, universal_newlines=True).stdout.read()
openrc = True if 'openrc' in rc_system else False


def datafilelist(installbase, sourcebase):
    datafileList = []
    for root, subFolders, files in os.walk(sourcebase):
        fileList = []
        for f in files:
            fileList.append(os.path.join(root, f))
        datafileList.append((root.replace(sourcebase, installbase), fileList))
    return datafileList


share_networkmgr = [
    'src/authentication.py',
    'src/net_api.py',
    'src/trayicon.py'
]

data_files = [
    (f'{prefix}/etc/devd', ['src/setupnic.conf']),
    (f'{prefix}/etc/xdg/autostart', ['src/networkmgr.desktop']),
    (f'{prefix}/share/networkmgr', share_networkmgr),
    (f'{prefix}/etc/sudoers.d', ['src/sudoers.d/networkmgr'])
]

if openrc is True:
    data_files.append((f'{prefix}/etc/devd-openrc', ['src/setupnic.conf']))

data_files.extend(datafilelist(f'{prefix}/share/icons/hicolor', 'src/icons'))

setup(
    name="networkmgr",
    version=PROGRAM_VERSION,
    description="Networkmgr is a tool to manage FreeBSD/GHostBSD network",
    license='BSD',
    author='Eric Turgeon',
    url='https://github/GhostBSD/networkmgr/',
    package_dir={'': '.'},
    data_files=data_files,
    install_requires=['setuptools'],
    scripts=['networkmgr', 'src/netcardmgr', 'src/setup-nic']
)

run('gtk-update-icon-cache -f /usr/local/share/icons/hicolor', shell=True)
