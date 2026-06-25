"""Tests for the TokenSecurity provider and the SecurityConfig factory."""

from __future__ import annotations

import logging
import socket
import threading

import pytest

from tsanet.common.config import SecurityConfig
from tsanet.common.errors import AuthenticationError, SecurityNotImplementedError
from tsanet.protocol.security import NullSecurity, TokenSecurity
from tsanet.protocol.transport import TCP


def _connected_socket_pair() -> tuple[socket.socket, socket.socket]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(listener.getsockname())
    server, _ = listener.accept()
    listener.close()
    return server, client


class TestTokenSecurity:
    def test_matching_token_succeeds(self):
        server_sock, client_sock = _connected_socket_pair()
        security = TokenSecurity("shared-secret")
        results: dict[str, object] = {}

        def serve():
            try:
                security.wrap(server_sock, server=True)
                results["server"] = "ok"
            except Exception as exc:  # noqa: BLE001
                results["server"] = exc

        t = threading.Thread(target=serve)
        t.start()
        try:
            security.wrap(client_sock, server=False)
        finally:
            t.join(timeout=5)

        assert results["server"] == "ok"
        client_sock.sendall(b"ping")
        assert server_sock.recv(4) == b"ping"
        client_sock.close()
        server_sock.close()

    def test_mismatched_token_raises_on_both_sides(self):
        server_sock, client_sock = _connected_socket_pair()
        server_security = TokenSecurity("correct")
        client_security = TokenSecurity("wrong")
        results: dict[str, object] = {}

        def serve():
            try:
                server_security.wrap(server_sock, server=True)
                results["server"] = "ok"
            except Exception as exc:  # noqa: BLE001
                results["server"] = exc

        t = threading.Thread(target=serve)
        t.start()
        try:
            with pytest.raises(AuthenticationError):
                client_security.wrap(client_sock, server=False)
        finally:
            t.join(timeout=5)
            client_sock.close()

        assert isinstance(results["server"], AuthenticationError)

    def test_warns_on_non_loopback(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tsanet.protocol"):
            TokenSecurity("secret").warn_if_insecure(TCP, "0.0.0.0")
        assert any("sent in the clear" in record.message for record in caplog.records)

    def test_quiet_on_loopback(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tsanet.protocol"):
            TokenSecurity("secret").warn_if_insecure(TCP, "127.0.0.1")
        assert caplog.records == []


class TestBuildProvider:
    def test_none_mode_builds_null_security(self):
        assert isinstance(SecurityConfig(mode="none").build_provider(), NullSecurity)

    def test_token_mode_builds_token_security(self):
        provider = SecurityConfig(mode="token", token="abc").build_provider()
        assert isinstance(provider, TokenSecurity)

    def test_tls_token_mode_not_implemented(self):
        config = SecurityConfig(
            mode="tls-token", token="abc", tls_cert="cert.pem", tls_key="key.pem"
        )
        with pytest.raises(SecurityNotImplementedError):
            config.build_provider()
