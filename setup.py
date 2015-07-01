#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2015 by Mike Gabriel <mike.gabriel@das-netzwerkteam.de>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.

import os
import sys

from glob import glob

from setuptools import setup

# import DistUtilsExtra.command.build_extra
# import DistUtilsExtra.command.build_i18n
# import DistUtilsExtra.command.clean_i18n

# to update i18n .mo files (and merge .pot file into .po files) run on Linux:
# ,,python setup.py build_i18n -m''

# silence pyflakes, __VERSION__ is properly assigned below...
__VERSION__ = '1.0'
# for line in file('networkmgr').readlines():
#    if (line.startswith('__VERSION__')):
#        exec(line.strip())
PROGRAM_VERSION = __VERSION__

def datafilelist(installbase, sourcebase):
    datafileList = []
    for root, subFolders, files in os.walk(sourcebase):
        fileList = []
        for f in files:
            fileList.append(os.path.join(root, f))
        datafileList.append((root.replace(sourcebase, installbase), fileList))
    return datafileList
# '{prefix}/share/man/man1'.format(prefix=sys.prefix), glob('data/*.1')),
data_files = [
    ('{prefix}/etc/xdg/autostart'.format(prefix=sys.prefix), ['src/networkmgr.desktop',]),
    ('{prefix}/share/networkmgr'.format(prefix=sys.prefix), ['src/authentication.py',]),
    ('{prefix}/share/networkmgr'.format(prefix=sys.prefix), ['src/detect-nics.sh',]),
    ('{prefix}/share/networkmgr'.format(prefix=sys.prefix), ['src/detect-wifi.sh',]),
    ('{prefix}/share/networkmgr'.format(prefix=sys.prefix), ['src/enable-net.sh',]),
    ('{prefix}/share/networkmgr'.format(prefix=sys.prefix), ['src/net_api.py',]),
    ('{prefix}/share/networkmgr'.format(prefix=sys.prefix), ['src/netcardmgr.py',]),
    ('{prefix}/share/networkmgr'.format(prefix=sys.prefix), ['src/test-netup.sh',]),
    ('{prefix}/share/networkmgr'.format(prefix=sys.prefix), ['src/trayicon.py',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-adhoc.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-device-wired-autoip.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-device-wired.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-device-wireless.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-device-wwan.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-mb-roam.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-no-connection.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-secure-lock.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-signal-0-secure.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-signal-0.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-signal-00-secure.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-signal-00.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-signal-100-secure.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-signal-100.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-signal-25-secure.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-signal-25.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-signal-50-secure.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-signal-50.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-signal-75-secure.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-signal-75.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-tech-3g.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-tech-cdma-1x.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-tech-edge.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-tech-evdo.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-tech-gprs.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-tech-hspa.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-tech-umts.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-vpn-active-lock.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-vpn-connecting12.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-vpn-connecting13.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-vpn-connecting14.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-vpn-lock.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-vpn-standalone-lock.png',]),
    ('{prefix}/share/networkmgr/icons'.format(prefix=sys.prefix), ['src/icons/nm-wwan-tower.png',]),
]
data_files.extend(datafilelist('{prefix}/share/locale'.format(prefix=sys.prefix), 'build/mo'))

# cmdclass ={
#             "build" : DistUtilsExtra.command.build_extra.build_extra,
#             "build_i18n" :  DistUtilsExtra.command.build_i18n.build_i18n,
#             "clean": DistUtilsExtra.command.clean_i18n.clean_i18n,
# }

setup(
    name = "networkmgr",
    version = PROGRAM_VERSION,
    description = "Networkmgr is a tool to manage FreeBSD/GHostBSD network",
    license = 'BSD',
    author = 'Eric Turgeon',
    url = 'https://github/GhostBSD/networkmgr/',
    package_dir = {'': '.'},
    data_files = data_files,
    install_requires = [ 'setuptools', ],
    scripts = ['networkmgr'],
)
# cmdclass = cmdclass,