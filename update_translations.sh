#!/usr/bin/env sh

xgettext src/trayicon.py -o src/locale/networkmgr.pot

msgmerge -U src/locale/zh_CN/networkmgr.po src/locale/networkmgr.pot
