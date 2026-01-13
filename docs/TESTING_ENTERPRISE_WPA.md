# Testing Enterprise WPA with FreeRADIUS

This document describes how to set up a test environment for Enterprise WPA (WPA2-Enterprise/802.1X) on FreeBSD/GhostBSD using FreeRADIUS and hostapd.

## Requirements

- FreeBSD/GhostBSD system
- A wireless card that supports AP mode (for hostapd)
- Another wireless card (or separate machine) for testing as a client

## Installation

### 1. Install FreeRADIUS

```bash
pkg install freeradius3
```

### 2. Install hostapd (if creating test AP)

```bash
pkg install hostapd
```

## FreeRADIUS Configuration

### Basic Setup

1. Configure test users in `/usr/local/etc/raddb/users`:

```
# Test user for PEAP/MSCHAPV2
testuser    Cleartext-Password := "testpassword"

# Test user with specific attributes
enterpriseuser  Cleartext-Password := "enterprise123"
                Reply-Message = "Welcome to Enterprise Network"
```

2. Configure clients (APs) in `/usr/local/etc/raddb/clients.conf`:

```
client localhost {
    ipaddr = 127.0.0.1
    secret = testing123
}

client testap {
    ipaddr = 192.168.1.0/24
    secret = radiussecret
}
```

3. Enable EAP in `/usr/local/etc/raddb/mods-enabled/eap`:

```
eap {
    default_eap_type = peap

    tls-config tls-common {
        private_key_file = /usr/local/etc/raddb/certs/server.key
        certificate_file = /usr/local/etc/raddb/certs/server.pem
        ca_file = /usr/local/etc/raddb/certs/ca.pem
        dh_file = /usr/local/etc/raddb/certs/dh
        random_file = /dev/urandom
        ca_path = /usr/local/etc/raddb/certs
    }

    tls {
        tls = tls-common
    }

    peap {
        tls = tls-common
        default_eap_type = mschapv2
        virtual_server = inner-tunnel
    }

    ttls {
        tls = tls-common
        default_eap_type = mschapv2
        virtual_server = inner-tunnel
    }

    mschapv2 {
    }
}
```

### Generate Test Certificates

Create test certificates for the RADIUS server:

```bash
cd /usr/local/etc/raddb/certs

# Generate CA
openssl genrsa -out ca.key 2048
openssl req -new -x509 -days 365 -key ca.key -out ca.pem \
    -subj "/C=US/ST=Test/L=Test/O=TestOrg/CN=Test CA"

# Generate server certificate
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
    -subj "/C=US/ST=Test/L=Test/O=TestOrg/CN=radius.test.local"
openssl x509 -req -days 365 -in server.csr -CA ca.pem -CAkey ca.key \
    -CAcreateserial -out server.pem

# Generate DH parameters
openssl dhparam -out dh 2048

# Set permissions
chmod 640 *.key *.pem
chown root:wheel *.key *.pem
```

### Start FreeRADIUS

```bash
# Test configuration
radiusd -X

# Or start as service
service radiusd enable
service radiusd start
```

## hostapd Configuration (Test AP)

Create `/usr/local/etc/hostapd.conf`:

```
interface=wlan0
driver=bsd
ssid=TestEnterprise
hw_mode=g
channel=6
auth_algs=1
wpa=2
wpa_key_mgmt=WPA-EAP
rsn_pairwise=CCMP

# RADIUS server settings
ieee8021x=1
own_ip_addr=192.168.1.1
nas_identifier=test-ap

auth_server_addr=127.0.0.1
auth_server_port=1812
auth_server_shared_secret=testing123

acct_server_addr=127.0.0.1
acct_server_port=1813
acct_server_shared_secret=testing123
```

Start hostapd:

```bash
# Create wlan interface in AP mode
ifconfig wlan0 create wlandev ath0 wlanmode hostap

# Start hostapd
hostapd /usr/local/etc/hostapd.conf
```

## Testing with NetworkMgr

1. Scan for networks - the TestEnterprise network should show as WPA2-EAP
2. Click on the network to open the Enterprise Authentication dialog
3. Enter test credentials:
   - EAP Method: PEAP
   - Inner Auth: MSCHAPV2
   - Username: testuser
   - Password: testpassword
   - CA Certificate: /usr/local/etc/raddb/certs/ca.pem (or leave empty for testing)

## Testing with wpa_supplicant directly

Create a test configuration `/tmp/test_eap.conf`:

```
network={
    ssid="TestEnterprise"
    key_mgmt=WPA-EAP
    eap=PEAP
    identity="testuser"
    password="testpassword"
    phase2="auth=MSCHAPV2"
    # ca_cert="/usr/local/etc/raddb/certs/ca.pem"
}
```

Test connection:

```bash
wpa_supplicant -i wlan0 -c /tmp/test_eap.conf -d
```

## Troubleshooting

### Check RADIUS logs

```bash
# Run in debug mode
radiusd -X

# Check log file
tail -f /var/log/radius.log
```

### Check wpa_supplicant status

```bash
wpa_cli -i wlan0 status
wpa_cli -i wlan0 scan_results
```

### Common Issues

1. **Certificate verification failed**: Use `ca_cert` parameter or temporarily disable with `phase1="peaplabel=0"` for testing only.

2. **Authentication rejected**: Check username/password in FreeRADIUS users file.

3. **EAP method not supported**: Ensure the EAP module is enabled in FreeRADIUS.

## Unit Tests

Run the enterprise WPA unit tests:

```bash
cd /path/to/networkmgr
pytest -v tests/unit/test_enterprise_wpa.py
```

## Security Notes

- The test setup uses weak secrets and self-signed certificates
- Do not use in production environments
- Always use proper CA certificates in production
- Protect wpa_supplicant.conf (should be mode 0600)
