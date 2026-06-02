"""Unit tests for http_request SSRF validation logic.

Pure logic tests: no real HTTP requests, no network I/O.
Mocks socket.getaddrinfo for DNS resolution tests.
"""

import sys
import os
import socket
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.tools.http_request import (
    _is_private_ip,
    _try_parse_decimal_ip,
    _validate_url_against_ssrf,
)


class TestIsPrivateIp:
    def test_loopback_127_0_0_1(self):
        assert _is_private_ip("127.0.0.1") is True

    def test_private_192_168(self):
        assert _is_private_ip("192.168.1.1") is True

    def test_private_10_x(self):
        assert _is_private_ip("10.0.0.1") is True

    def test_private_172_16(self):
        assert _is_private_ip("172.16.0.1") is True

    def test_link_local_169_254(self):
        assert _is_private_ip("169.254.1.1") is True

    def test_public_ip(self):
        assert _is_private_ip("8.8.8.8") is False

    def test_public_ip_cloudflare(self):
        assert _is_private_ip("1.1.1.1") is False

    def test_invalid_string(self):
        assert _is_private_ip("not-an-ip") is False

    def test_ipv6_loopback(self):
        assert _is_private_ip("::1") is True

    def test_ipv6_private(self):
        assert _is_private_ip("fc00::1") is True


class TestTryParseDecimalIp:
    def test_decimal_2130706433(self):
        result = _try_parse_decimal_ip("2130706433")
        assert result == "127.0.0.1"

    def test_hex_ip(self):
        result = _try_parse_decimal_ip("0x7f000001")
        assert result == "127.0.0.1"

    def test_non_numeric(self):
        result = _try_parse_decimal_ip("example.com")
        assert result is None

    def test_too_large_for_ipv6(self):
        result = _try_parse_decimal_ip("9999999999999999999999999999999999999999")
        assert result is None

    def test_large_but_valid_ipv6_range(self):
        result = _try_parse_decimal_ip("9999999999999999999999")
        assert result is not None

    def test_zero(self):
        result = _try_parse_decimal_ip("0")
        assert result == "0.0.0.0"


class TestValidateUrlAgainstSsrf:
    def test_block_localhost(self):
        err = _validate_url_against_ssrf("http://localhost:8080/api")
        assert err is not None
        assert "localhost" in err

    def test_block_127_0_0_1(self):
        err = _validate_url_against_ssrf("http://127.0.0.1:3000/")
        assert err is not None
        assert "127.0.0.1" in err

    def test_block_0_0_0_0(self):
        err = _validate_url_against_ssrf("http://0.0.0.0:8080/")
        assert err is not None
        assert "0.0.0.0" in err

    def test_block_metadata_google_internal(self):
        err = _validate_url_against_ssrf("http://metadata.google.internal/")
        assert err is not None

    def test_block_169_254_169_254(self):
        err = _validate_url_against_ssrf("http://169.254.169.254/metadata")
        assert err is not None

    def test_block_private_192_168(self):
        err = _validate_url_against_ssrf("http://192.168.1.1/admin")
        assert err is not None
        assert "192.168" in err

    def test_block_private_10_x(self):
        err = _validate_url_against_ssrf("http://10.0.0.5:8080/")
        assert err is not None
        assert "10." in err

    def test_block_private_172_16(self):
        err = _validate_url_against_ssrf("http://172.16.0.1/")
        assert err is not None

    def test_block_decimal_ip_bypass(self):
        err = _validate_url_against_ssrf("http://2130706433/")
        assert err is not None

    def test_block_ipv6_loopback(self):
        err = _validate_url_against_ssrf("http://[::1]:8080/")
        assert err is not None

    @patch("app.tools.http_request.socket.getaddrinfo")
    def test_allow_public_domain(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))
        ]
        err = _validate_url_against_ssrf("https://api.example.com/v1/data")
        assert err is None

    def test_allow_public_ip(self):
        err = _validate_url_against_ssrf("http://8.8.8.8/")
        assert err is None

    def test_allow_cloudflare(self):
        err = _validate_url_against_ssrf("https://1.1.1.1/dns-query")
        assert err is None

    @patch("app.tools.http_request.socket.getaddrinfo")
    def test_block_domain_resolving_to_private_ip(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.100", 0))
        ]
        err = _validate_url_against_ssrf("http://evil.internal.example.com/")
        assert err is not None
        assert "192.168" in err

    @patch("app.tools.http_request.socket.getaddrinfo")
    def test_allow_domain_resolving_to_public_ip(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))
        ]
        err = _validate_url_against_ssrf("http://example.com/")
        assert err is None

    def test_empty_hostname(self):
        err = _validate_url_against_ssrf("http:///path")
        assert err is not None
        assert "no hostname" in err
