#!/bin/sh
NIC="$1"
ifconfig ${NIC} | grep -q "802.11" 2>/dev/null
if [ $? -eq 0 ]; then
  echo '0'
else 
  echo '1'
fi
