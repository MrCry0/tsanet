"""Tests for configuration models and loading."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tsanet.common.config import NetworkConfig, SecurityConfig
from tsanet.hub.config import HubConfig
from tsanet.protocol.transport import TCP, UNIX


def test_hub_defaults():
    config = HubConfig()
    assert config.network.mode == "listen"
    assert config.network.transport == TCP
    assert config.network.port == 7777
    assert config.security.mode == "none"


def test_network_endpoint_tcp():
    endpoint = NetworkConfig(transport="tcp", address="127.0.0.1", port=9000).endpoint()
    assert (endpoint.transport, endpoint.address, endpoint.port) == (TCP, "127.0.0.1", 9000)


def test_network_endpoint_unix_drops_port():
    endpoint = NetworkConfig(transport="unix", address="/tmp/s.sock", port=7777).endpoint()
    assert endpoint.transport == UNIX
    assert endpoint.port is None


def test_network_tcp_requires_port():
    with pytest.raises(ValidationError):
        NetworkConfig(transport="tcp", port=None)


def test_security_token_requires_token():
    with pytest.raises(ValidationError):
        SecurityConfig(mode="token")


def test_security_tls_requires_cert_and_key():
    with pytest.raises(ValidationError):
        SecurityConfig(mode="tls-token", token="secret")


def test_hub_load_from_yaml(tmp_path):
    path = tmp_path / "hub.yaml"
    path.write_text(
        "network:\n  transport: unix\n  address: /run/tsanet.sock\npoll_interval: 5.0\n"
    )
    config = HubConfig.load(path)
    assert config.network.transport == UNIX
    assert config.poll_interval == 5.0


def test_hub_load_missing_file_uses_defaults(tmp_path):
    config = HubConfig.load(tmp_path / "absent.yaml")
    assert config.network.port == 7777
