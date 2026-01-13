"""
Unit tests for Enterprise WPA (802.1X/EAP) functionality.
"""
import sys
import os
import tempfile
from pathlib import Path

import pytest

# Add project root to path
top_dir = str(Path(__file__).absolute().parent.parent.parent)
sys.path.insert(0, top_dir)

from NetworkMgr.net_api import (
    EAP_METHODS,
    PHASE2_METHODS,
    DEFAULT_CA_CERT,
    is_enterprise_network,
    get_security_type,
    validate_certificate,
    get_system_ca_certificates,
    generate_eap_config,
)


class TestEnterpriseDetection:
    """Tests for enterprise network detection."""

    def test_is_enterprise_network_with_eap(self):
        """Test detection of EAP indicator."""
        assert is_enterprise_network("RSN-EAP WPA2-EAP") is True
        assert is_enterprise_network("WPA2-EAP") is True
        assert is_enterprise_network("EAP") is True

    def test_is_enterprise_network_with_8021x(self):
        """Test detection of 802.1X indicator."""
        assert is_enterprise_network("RSN 802.1X") is True
        assert is_enterprise_network("802.1X WPA2") is True

    def test_is_enterprise_network_psk(self):
        """Test that PSK networks are not detected as enterprise."""
        assert is_enterprise_network("RSN WPA2-PSK") is False
        assert is_enterprise_network("WPA-PSK") is False
        assert is_enterprise_network("RSN HTCAP WME") is False

    def test_is_enterprise_network_open(self):
        """Test that open networks are not detected as enterprise."""
        assert is_enterprise_network("") is False
        assert is_enterprise_network("ESS") is False

    def test_is_enterprise_network_case_insensitive(self):
        """Test case-insensitive detection."""
        assert is_enterprise_network("wpa2-eap") is True
        assert is_enterprise_network("Eap") is True


class TestSecurityTypeDetection:
    """Tests for security type detection."""

    def test_get_security_type_wpa2_eap(self):
        """Test WPA2-EAP detection."""
        assert get_security_type("RSN WPA2-EAP") == "WPA2-EAP"
        assert get_security_type("RSN EAP") == "WPA2-EAP"

    def test_get_security_type_wpa_eap(self):
        """Test WPA-EAP detection."""
        assert get_security_type("WPA EAP") == "WPA-EAP"

    def test_get_security_type_wpa2_psk(self):
        """Test WPA2-PSK detection."""
        assert get_security_type("RSN HTCAP WME") == "WPA2-PSK"
        # Bare RSN without consumer features is classified as enterprise
        assert get_security_type("RSN") == "WPA2-EAP"

    def test_get_security_type_wpa_psk(self):
        """Test WPA-PSK detection."""
        assert get_security_type("WPA HTCAP") == "WPA-PSK"

    def test_get_security_type_wep(self):
        """Test WEP detection."""
        assert get_security_type("WEP") == "WEP"
        assert get_security_type("PRIVACY") == "WEP"

    def test_get_security_type_open(self):
        """Test open network detection."""
        assert get_security_type("") == "OPEN"
        assert get_security_type("ESS") == "OPEN"


class TestCertificateValidation:
    """Tests for certificate validation."""

    def test_validate_certificate_empty_path(self):
        """Test validation with empty path."""
        is_valid, error = validate_certificate("")
        assert is_valid is False
        assert "No certificate path" in error

    def test_validate_certificate_none_path(self):
        """Test validation with None path."""
        is_valid, error = validate_certificate(None)
        assert is_valid is False

    def test_validate_certificate_nonexistent(self):
        """Test validation with nonexistent file."""
        is_valid, error = validate_certificate("/nonexistent/cert.pem")
        assert is_valid is False
        assert "not found" in error

    def test_validate_certificate_directory(self):
        """Test validation with directory instead of file."""
        is_valid, error = validate_certificate("/tmp")
        assert is_valid is False
        assert "Not a file" in error

    def test_validate_certificate_valid_file(self):
        """Test validation with valid readable file."""
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(b"test certificate content")
            temp_path = f.name
        try:
            is_valid, error = validate_certificate(temp_path)
            assert is_valid is True
            assert error is None
        finally:
            os.unlink(temp_path)


class TestEapConfigGeneration:
    """Tests for EAP configuration generation."""

    def test_generate_eap_config_peap(self):
        """Test PEAP configuration generation."""
        config = {
            'eap_method': 'PEAP',
            'identity': 'testuser',
            'password': 'testpass',
            'phase2': 'MSCHAPV2',
        }
        result = generate_eap_config("TestNetwork", config)

        assert 'ssid="TestNetwork"' in result
        assert 'key_mgmt=WPA-EAP' in result
        assert 'eap=PEAP' in result
        assert 'identity="testuser"' in result
        assert 'password="testpass"' in result
        assert 'phase2="auth=MSCHAPV2"' in result

    def test_generate_eap_config_ttls(self):
        """Test TTLS configuration generation."""
        config = {
            'eap_method': 'TTLS',
            'identity': 'user@domain.com',
            'password': 'secret',
            'phase2': 'PAP',
            'ca_cert': '/etc/ssl/certs/ca.pem',
        }
        result = generate_eap_config("CorpWifi", config)

        assert 'eap=TTLS' in result
        assert 'identity="user@domain.com"' in result
        assert 'phase2="auth=PAP"' in result
        assert 'ca_cert="/etc/ssl/certs/ca.pem"' in result

    def test_generate_eap_config_tls(self):
        """Test TLS (certificate-based) configuration generation."""
        config = {
            'eap_method': 'TLS',
            'identity': 'client@corp.com',
            'client_cert': '/etc/ssl/client.pem',
            'private_key': '/etc/ssl/client.key',
            'private_key_passwd': 'keypass',
            'ca_cert': '/etc/ssl/ca.pem',
        }
        result = generate_eap_config("SecureNet", config)

        assert 'eap=TLS' in result
        assert 'identity="client@corp.com"' in result
        assert 'client_cert="/etc/ssl/client.pem"' in result
        assert 'private_key="/etc/ssl/client.key"' in result
        assert 'private_key_passwd="keypass"' in result
        assert 'password=' not in result  # TLS doesn't use password

    def test_generate_eap_config_with_anonymous_identity(self):
        """Test configuration with anonymous identity."""
        config = {
            'eap_method': 'PEAP',
            'identity': 'realuser',
            'password': 'pass',
            'anonymous_identity': 'anonymous@domain.com',
        }
        result = generate_eap_config("AnonNet", config)

        assert 'anonymous_identity="anonymous@domain.com"' in result

    def test_generate_eap_config_with_domain_match(self):
        """Test configuration with domain suffix match."""
        config = {
            'eap_method': 'PEAP',
            'identity': 'user',
            'password': 'pass',
            'domain_suffix_match': 'radius.company.com',
        }
        result = generate_eap_config("SecNet", config)

        assert 'domain_suffix_match="radius.company.com"' in result


class TestEapConstants:
    """Tests for EAP-related constants."""

    def test_eap_methods_defined(self):
        """Test that EAP methods are defined."""
        assert 'PEAP' in EAP_METHODS
        assert 'TTLS' in EAP_METHODS
        assert 'TLS' in EAP_METHODS

    def test_phase2_methods_defined(self):
        """Test that Phase 2 methods are defined."""
        assert 'MSCHAPV2' in PHASE2_METHODS
        assert 'GTC' in PHASE2_METHODS
        assert 'PAP' in PHASE2_METHODS

    def test_default_ca_cert_path(self):
        """Test default CA certificate path is set."""
        assert DEFAULT_CA_CERT == '/etc/ssl/certs/ca-root-nss.crt'
