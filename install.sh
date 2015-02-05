#!/bin/sh

if [ -z "$1" ] ; then
  LOCALBASE=/usr/local
else
  LOCALBASE="$1"
fi

if [ -d "${LOCALBASE}/share/networkmgr" ] ; then
  rm -rf ${LOCALBASE}/share/networkmgr
fi

mkdir -p ${LOCALBASE}/share/networkmgr 

cp -rf networkmgr/* ${LOCALBASE}/share/networkmgr/ 

if [ ! -d "${LOCALBASE}etc/xdg/autostart" ] ; then
  mkdir -p ${LOCALBASE}etc/xdg/autostart/
fi

cp -f networkmgr.desktop ${LOCALBASE}etc/xdg/autostart/networkmgr.desktop

# Install the executable
if [ ! -d "${LOCALBASE}/bin" ] ; then
  mkdir -p ${LOCALBASE}/bin
fi

cp networkmgr.py ${LOCALBASE}/bin/networkmgr
chown root:wheel ${LOCALBASE}/bin/networkmgr
chmod 755 ${LOCALBASE}/bin/networkmgr
