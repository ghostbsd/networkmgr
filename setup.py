#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from platform import system
from setuptools import setup
from subprocess import run

__VERSION__ = '6.1'
PROGRAM_VERSION = __VERSION__

prefix = '/usr/local' if system() == 'FreeBSD' else sys.prefix


def datafilelist(installbase, sourcebase):
    datafileList = []
    for root, subFolders, files in os.walk(sourcebase):
        fileList = [os.path.join(root, f) for f in files]
        datafileList.append((root.replace(sourcebase, installbase), fileList))
    return datafileList


share_networkmgr = [
    'src/auto-switch.py',
    'src/net_api.py',
    'src/setup-nic.py',
    'src/trayicon.py'
]

data_files = [
    (f'{prefix}/etc/xdg/autostart', ['src/networkmgr.desktop']),
    (f'{prefix}/share/networkmgr', share_networkmgr),
    (f'{prefix}/etc/sudoers.d', ['src/sudoers.d/networkmgr'])
]

if os.path.exists('/etc/devd'):
    data_files.append((f'{prefix}/etc/devd', ['src/networkmgr.conf']))
if os.path.exists('/etc/devd-openrc'):
    data_files.append((f'{prefix}/etc/devd-openrc', ['src/networkmgr.conf']))

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
    scripts=['networkmgr', 'src/netcardmgr']
)

run('gtk-update-icon-cache -f /usr/local/share/icons/hicolor', shell=True)
