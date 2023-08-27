#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from platform import system
from setuptools import setup
from subprocess import run

__VERSION__ = '6.3'
PROGRAM_VERSION = __VERSION__

prefix = '/usr/local' if system() == 'FreeBSD' else sys.prefix

# compiling translations
os.system("sh compile_translations.sh")


def datafilelist(installbase, sourcebase):
    datafileList = []
    for root, subFolders, files in os.walk(sourcebase):
        fileList = []
        for f in files:
            fileList.append(os.path.join(root, f))
        datafileList.append((root.replace(sourcebase, installbase), fileList))
    return datafileList


networkmgr_share = [
    'src/auto-switch.py',
    'src/setup-nic.py'
]

data_files = [
    (f'{prefix}/etc/xdg/autostart', ['src/networkmgr.desktop']),
    (f'{prefix}/share/networkmgr', networkmgr_share),
    (f'{prefix}/share/locale/zh_CN/LC_MESSAGES', ['src/locale/zh_CN/networkmgr.mo']),
    (f'{prefix}/share/locale/ru/LC_MESSAGES', ['src/locale/ru/networkmgr.mo']),
    (f'{prefix}/etc/sudoers.d', ['src/sudoers.d/networkmgr'])
]

if os.path.exists('/etc/devd'):
    data_files.append((f'{prefix}/etc/devd', ['src/networkmgr.conf']))
if os.path.exists('/etc/devd-openrc'):
    data_files.append((f'{prefix}/etc/devd-openrc', ['src/networkmgr.conf']))

data_files.extend(datafilelist(f'{prefix}/share/icons/hicolor', 'src/icons'))

setup(
    name="NetworkMgr",
    version=PROGRAM_VERSION,
    description="NetworkMgr is a tool to manage FreeBSD/GhostBSD network",
    license='BSD',
    author='Eric Turgeon',
    url='https://github/GhostBSD/networkmgr/',
    package_dir={'': '.'},
    data_files=data_files,
    install_requires=['setuptools'],
    packages=['NetworkMgr'],
    scripts=['networkmgr', 'networkmgr_configuration']
)

run('gtk-update-icon-cache -f /usr/local/share/icons/hicolor', shell=True)
