#!/bin/sh

if [ -z "$1" ] ; then
  LOCALBASE=/usr/local
else
  LOCALBASE="$1"
fi

share = "/usr/local/share/networkmgr"
sudoers = "/usr/local/etc/sudoers"
sudoline = '%wheel ALL=(ALL) NOPASSWD: /usr/local/share/networkmgr/trayicon.py'
sudo = "# %wheel ALL=(ALL) NOPASSWD: ALL"
deskfile = "/usr/local/etc/xdg/autostart/networkmgr.desktop"

if [ -d "${LOCALBASE}/share/networkmgr" ] ; then
  rm -rf ${LOCALBASE}/share/networkmgr
fi

mkdir -p ${LOCALBASE}/share/networkmgr

if [ ! -d "${LOCALBASE}etc/xdg/autostart" ] ; then
  mkdir -p ${LOCALBASE}etc/xdg/autostart/
fi

cp -f networkmgr.sh ${LOCALBASE}etc/xdg/autostart/networkmgr.desktop

# Install the executable
if [ ! -d "${LOCALBASE}/bin" ] ; then
  mkdir -p ${LOCALBASE}/bin
fi

cp networkmgr.sh ${LOCALBASE}/bin/networkmgr
wchown root:wheel ${LOCALBASE}/bin/networkmgr
chmod 755 ${LOCALBASE}/bin/networkmgr
