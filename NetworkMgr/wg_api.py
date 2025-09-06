#!/usr/local/bin/python3.11

from platform import system
from subprocess import Popen, PIPE, run, check_output, os

prefix = '/usr/local' if system() == 'FreeBSD' else sys.prefix
wgconfigpath = f'{prefix}/etc/wireguard/'

def wg_service_state():
    run('service wireguard status', shell=True)

def wireguardDictionary():

    maindictionary = {
        'service': wg_service_state(),
        'default': '',
    }
    configs = {}

    if os.path.exists(wgconfigpath):
        wgconfigs = sorted(os.listdir(wgconfigpath))
        for wgconfig in wgconfigs:
            content = open(wgconfigpath + wgconfig)
            for line in content:
                if "# Name = " in line:
                    wgName = line.split('=')[1].strip()
            wgDevice = wgconfig.replace('.conf', '')
            wgState = wg_status(wgDevice)
            seconddictionary = { 'state': wgState, 'info': wgName }
            configs[wgDevice] = seconddictionary

        maindictionary['configs'] = configs

    return maindictionary


# def stopWG():
#     run('service wireguard stop', shell=True)


# def startWG():
#     run('service wireguard start', shell=True)


def disableWG(wgconfig):
    run(f'wg-quick down {wgconfig}', shell=True)


def enableWG(wgconfig):
    run(f'wg-quick up {wgconfig}', shell=True)


def wg_status(wgconfig):
    # out = Popen(
    #     f'wg show {wgconfig}',
    #     shell=True, stdout=PIPE, stderr=PIPE,
    #     universal_newlines=True
    # )
    result=run(['wg', 'show', wgconfig], stdout=PIPE, stderr=PIPE)
    out = result.stdout.decode('utf-8')
    error = result.stderr.decode('utf-8')
#    print (out)
#    print (error)
    if len(out) == 0 and 'Unable to access interface: Device not configured' in error:
        status = "Disconnected"
    else:
        status = "Connected"

    return status



