"""Integration tests for the hub server: listen, connect, request/response."""

from __future__ import annotations

import threading

import pytest

from tsanet.common.config import NetworkConfig, SecurityConfig
from tsanet.common.errors import AuthenticationError
from tsanet.hub.config import HubConfig
from tsanet.hub.server import HubServer
from tsanet.protocol.messages import Request, Response, Status
from tsanet.protocol.security import TokenSecurity
from tsanet.protocol.transport import Endpoint, TCP, dial


def _tcp_config(mode="listen", port=0, security=None):
    return HubConfig(
        network=NetworkConfig(mode=mode, transport="tcp", address="127.0.0.1", port=port),
        security=security or SecurityConfig(),
        poll_interval=60.0,
    )


class _ReadyServer(HubServer):
    """HubServer that signals when its listener is bound and ready."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ready = threading.Event()

    def _accept_loop(self):
        self._ready.set()
        super()._accept_loop()


def _start_server(config=None):
    config = config or _tcp_config(port=0)
    server = _ReadyServer(config)
    t = threading.Thread(target=server.start, daemon=True)
    t.start()

    if not server._ready.wait(timeout=3.0):
        server.stop()
        raise RuntimeError("server did not start in time")

    port = server._listener.port
    return server, port


def _connect(port):
    return dial(Endpoint(TCP, "127.0.0.1", port))


# -- basic request / response ----------------------------------------------


class TestHubServer:
    def test_accepts_connection(self):
        server, port = _start_server()
        try:
            conn = _connect(port)
            conn.send(Request(id=1, domain="session", op="status"))
            resp = conn.recv()
            assert isinstance(resp, Response)
            assert resp.id == 1
            assert resp.status == Status.OK
            assert resp.data["active"] is True
            conn.close()
        finally:
            server.stop()

    def test_rejects_second_connection(self):
        server, port = _start_server()
        try:
            conn1 = _connect(port)
            conn2 = _connect(port)

            resp = conn2.recv()
            assert resp.status == Status.ERROR
            assert "already active" in resp.error.lower()

            conn1.close()
            conn2.close()
        finally:
            server.stop()

    def test_multiple_requests(self):
        server, port = _start_server()
        try:
            conn = _connect(port)
            for i in range(5):
                conn.send(Request(id=i, domain="session", op="status"))
                resp = conn.recv()
                assert resp.id == i
                assert resp.status == Status.OK
            conn.close()
        finally:
            server.stop()

    def test_session_disconnect(self):
        server, port = _start_server()
        try:
            conn = _connect(port)
            conn.send(Request(id=1, domain="session", op="disconnect"))
            resp = conn.recv()
            assert resp.status == Status.OK
            assert resp.data == {"active": False}
            conn.close()
        finally:
            server.stop()

    def test_unknown_domain_returns_error(self):
        server, port = _start_server()
        try:
            conn = _connect(port)
            conn.send(Request(id=7, domain="nonexistent", op="foo"))
            resp = conn.recv()
            assert resp.status == Status.ERROR
            assert "unknown domain" in resp.error.lower()
            conn.close()
        finally:
            server.stop()

    def test_session_force_takeover_lets_next_connection_in(self):
        server, port = _start_server()
        try:
            conn1 = _connect(port)
            conn1.send(Request(id=1, domain="session", op="status"))
            assert conn1.recv().status == Status.OK

            # Second connection is rejected.
            conn2 = _connect(port)
            reject = conn2.recv()
            assert reject.status == Status.ERROR
            conn2.close()

            # conn1 allows takeover.
            conn1.send(Request(id=2, domain="session", op="force_takeover"))
            assert conn1.recv().status == Status.OK

            # conn3 connects and is admitted without force.
            conn3 = _connect(port)
            conn3.send(Request(id=1, domain="session", op="status"))
            resp3 = conn3.recv()
            assert resp3.status == Status.OK
            assert resp3.data["active"] is True

            conn1.close()
            conn3.close()
        finally:
            server.stop()

    def test_devices_list(self):
        server, port = _start_server()
        try:
            conn = _connect(port)
            conn.send(Request(id=1, domain="devices", op="list"))
            resp = conn.recv()
            assert resp.status == Status.OK
            assert isinstance(resp.data, list)
            conn.close()
        finally:
            server.stop()

    def test_dial_mode_config(self):
        config = _tcp_config(mode="dial", port=0)
        server = HubServer(config)
        assert server is not None


class TestHubServerTokenSecurity:
    def test_matching_token_connects(self):
        config = _tcp_config(security=SecurityConfig(mode="token", token="shared-secret"))
        server, port = _start_server(config)
        try:
            conn = dial(Endpoint(TCP, "127.0.0.1", port), TokenSecurity("shared-secret"))
            conn.send(Request(id=1, domain="session", op="status"))
            resp = conn.recv()
            assert resp.status == Status.OK
            conn.close()
        finally:
            server.stop()

    def test_mismatched_token_is_rejected_without_crashing_hub(self):
        config = _tcp_config(security=SecurityConfig(mode="token", token="shared-secret"))
        server, port = _start_server(config)
        try:
            with pytest.raises(AuthenticationError):
                dial(Endpoint(TCP, "127.0.0.1", port), TokenSecurity("wrong-secret"))

            # The hub must still be alive and accepting good connections.
            conn = dial(Endpoint(TCP, "127.0.0.1", port), TokenSecurity("shared-secret"))
            conn.send(Request(id=1, domain="session", op="status"))
            resp = conn.recv()
            assert resp.status == Status.OK
            conn.close()
        finally:
            server.stop()
