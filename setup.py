#!/usr/bin/env python3.6
# -*- coding: utf-8 -*-

import os
import sys

from setuptools import setup
from subprocess import run

# import DistUtilsExtra.command.build_extra
# import DistUtilsExtra.command.build_i18n
# import DistUtilsExtra.command.clean_i18n

# to update i18n .mo files (and merge .pot file into .po files) run on Linux:
# ,,python setup.py build_i18n -m''

# silence pyflakes, __VERSION__ is properly assigned below...
__VERSION__ = '3.0'
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
    ('{prefix}/etc/xdg/autostart'.format(prefix=sys.prefix),
        ['src/networkmgr.desktop']),
    ('{prefix}/share/networkmgr'.format(prefix=sys.prefix),
        ['src/authentication.py']),
    ('{prefix}/share/networkmgr'.format(prefix=sys.prefix),
        ['src/net_api.py']),
    ('{prefix}/share/networkmgr'.format(prefix=sys.prefix),
        ['src/trayicon.py']),
]

data_files.extend(datafilelist('{prefix}/share/icons/hicolor'.format(prefix=sys.prefix),
                  'src/icons'))

# cmdclass ={
#             "build" : DistUtilsExtra.command.build_extra.build_extra,
#             "build_i18n" :  DistUtilsExtra.command.build_i18n.build_i18n,
#             "clean": DistUtilsExtra.command.clean_i18n.clean_i18n,
# }

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

run('sudo gtk-update-icon-cache -f /usr/local/share/icons/hicolor', shell=True)
