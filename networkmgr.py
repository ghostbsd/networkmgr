#!/usr/local/bin/python

import os
from subprocess import Popen, PIPE
ncard = 'sh detect-nics.sh'
detect_wifi = 'sh detect-wifi.sh'
os.system("clear")
nics = Popen(ncard, shell=True, stdout=PIPE, close_fds=True)
netcard = nics.stdout


rconf = open('/etc/rc.conf', 'r')

for rc in rconf:
    if rc.rstrip() == 'ifconfig_wlan0="WPA DHCP"':
        print("Your WiFi card is already configured")
        if os.path.exists('/etc/rc.local'):
            os.remove('/etc/rc.local')
        quit()

for line in netcard:
    card = line.rstrip().partition(':')[0]
    find_wifi = Popen("%s %s" % (detect_wifi, card), shell=True, stdout=PIPE,
    close_fds=True)
    if find_wifi == 0:
        print("yes")
        #card = line.rstrip().partition(':')[0]
        #print '\n  Wireless card detected: %s' % card
        #print 'Setting %s card as default network card.' % card
        #rc = open('/etc/rc.conf', 'a')
        #rc.writelines('wlans_%s="wlan0"\n' % card)
        #rc.writelines('ifconfig_wlan0="WPA DHCP"\n')
        #rc.close()
        #if os.path.exists('/etc/wpa_supplicant.conf'):
            #pass
        #else:
            #wsc = open('/etc/wpa_supplicant.conf', 'w')
            #wsc.writelines('',)
        #call('/etc/rc.d/netif restart', shell=True)
        #call('ifconfig %s down' % card, shell=True)
        #call('ifconfig wlan0 down', shell=True)
        #call('ifconfig %s up' % card, shell=True)
        #call('ifconfig wlan0 up', shell=True)
        #quit()
#print '\n  No Wireless card detected.'
#if os.path.exists('/etc/rc.local'):
    #os.remove('/etc/rc.local')
