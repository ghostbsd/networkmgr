#!/usr/local/bin/python
#
# Copyright (c) 2012-2014, GhostBSD All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistribution's of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#
# 2. Redistribution's in binary form must reproduce the above
#    copyright notice,this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#
# 3. Neither then name of GhostBSD Project nor the names of its
#    contributors maybe used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES(INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# $Id: netcardmgr.py v 0.1 Saturday, February 08 2014 Eric Turgeon $

from subprocess import Popen, PIPE, call
ncard = 'sh /usr/local/share/networkmgr/detect-nics.sh'
detect_wifi = 'sh /usr/local/share/networkmgr/detect-wifi.sh'
nics = Popen(ncard, shell=True, stdout=PIPE, close_fds=True)
netcard = nics.stdout.readlines()

rcconf_out = open('/etc/rc.conf', 'r')
rcconf = rcconf_out.readlines()
netcardtext = 'Netork card configuration by Networkmgr'


class autoConfigure():

    def __init__(self):
        if any(netcardtext in listed for listed in rcconf):
            pass
        else:
            rc = open('/etc/rc.conf', 'a')
            rc.writelines('\n#%s\n' % netcardtext)
            rc.close()
        for line in netcard:
            card = line.rstrip().partition(' ')[0]
            if card != "wlan0":
                wifi = Popen("%s %s" % (detect_wifi, card), shell=True,
                stdout=PIPE, close_fds=True)
                answer = wifi.stdout.readlines()[0].strip()
                if answer == '0':
                    if any('wlans_%s=' % card in listed for listed in rcconf):
                        print("Your wifi network card is already configured.")
                    else:
                        rc = open('/etc/rc.conf', 'a')
                        rc.writelines('wlans_%s="wlan0"\n' % card)
                        rc.writelines('ifconfig_wlan0="WPA DHCP"\n')
                        rc.close()
                        call('/etc/rc.d/netif restart', shell=True)
                        call('ifconfig wlan0 up', shell=True)
                        call('/etc/rc.d/netif restart wlan0', shell=True)
                        print("Your WiFi card is ready to use.")
                else:
                    if any('ifconfig_%s=' % card in line for line in rcconf):
                        print("Your wired network card is already configured.")
                    else:
                        rc = open('/etc/rc.conf', 'a')
                        rc.writelines('ifconfig_%s="DHCP"\n' % card)
                        rc.close()
                        call('/etc/rc.d/netif restart', shell=True)
                        call('/etc/rc.d/netif restart wlan0', shell=True)
                        print("Your wired network card is configured.")
