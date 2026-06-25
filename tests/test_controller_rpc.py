"""Tests for the controller RPC client against a live hub."""

from __future__ import annotations

import threading

import pytest

from tsanet.common.config import NetworkConfig, SecurityConfig
from tsanet.common.errors import AuthenticationError
from tsanet.controller.config import ControllerConfig
from tsanet.controller.rpc_client import RpcClient, RpcError
from tsanet.hub.config import HubConfig
from tsanet.hub.server import HubServer


def _hub_config(port=0, security=None):
    return HubConfig(
        network=NetworkConfig(mode="listen", transport="tcp", address="127.0.0.1", port=port),
        security=security or SecurityConfig(),
        poll_interval=60.0,
    )


def _client_config(port, security=None):
    return ControllerConfig(
        network=NetworkConfig(mode="dial", transport="tcp", address="127.0.0.1", port=port),
        security=security or SecurityConfig(),
    )


class _ReadyHub(HubServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ready = threading.Event()

    def _accept_loop(self):
        self._ready.set()
        super()._accept_loop()


def _start_hub(config=None):
    config = config or _hub_config(port=0)
    hub = _ReadyHub(config)
    t = threading.Thread(target=hub.start, daemon=True)
    t.start()
    if not hub._ready.wait(timeout=3.0):
        hub.stop()
        raise RuntimeError("hub did not start")
    return hub, hub._listener.port


class TestRpcClient:
    def test_connect_and_call(self):
        hub, port = _start_hub()
        try:
            client = RpcClient(_client_config(port))
            client.connect()
            data = client.call("session", "status")
            assert data["active"] is True
            client.close()
        finally:
            hub.stop()

    def test_call_returns_error(self):
        hub, port = _start_hub()
        try:
            client = RpcClient(_client_config(port))
            client.connect()
            with pytest.raises(RpcError) as exc:
                client.call("nonexistent", "op")
            assert "unknown domain" in str(exc.value).lower()
            client.close()
        finally:
            hub.stop()

    def test_devices_list(self):
        hub, port = _start_hub()
        try:
            client = RpcClient(_client_config(port))
            client.connect()
            data = client.call("devices", "list")
            assert isinstance(data, list)
            client.close()
        finally:
            hub.stop()

    def test_not_connected_raises(self):
        client = RpcClient(_client_config(7777))
        with pytest.raises(Exception):
            client.call("session", "status")


class TestRpcClientTokenSecurity:
    def test_matching_token_connects_and_calls(self):
        token_security = SecurityConfig(mode="token", token="shared-secret")
        hub, port = _start_hub(_hub_config(port=0, security=token_security))
        try:
            client = RpcClient(_client_config(port, security=token_security))
            client.connect()
            data = client.call("session", "status")
            assert data["active"] is True
            client.close()
        finally:
            hub.stop()

    def test_mismatched_token_raises_authentication_error(self):
        hub, port = _start_hub(
            _hub_config(port=0, security=SecurityConfig(mode="token", token="shared-secret"))
        )
        try:
            client = RpcClient(
                _client_config(port, security=SecurityConfig(mode="token", token="wrong-secret"))
            )
            with pytest.raises(AuthenticationError):
                client.connect()
        finally:
            hub.stop()
