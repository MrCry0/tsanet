"""Loopback tests for listen/dial over tcp and unix, in both directions."""

from __future__ import annotations

import logging
import socket
import struct
import threading

import pytest

from tsanet.common.errors import ConnectionClosed
from tsanet.protocol.messages import Event, Request, Response, Status
from tsanet.protocol.security import NullSecurity, is_loopback
from tsanet.protocol.transport import TCP, UNIX, Connection, Endpoint, dial, listen


def _dial_endpoint(listener, bind: Endpoint) -> Endpoint:
    if bind.transport == TCP:
        return Endpoint(TCP, "127.0.0.1", listener.port)
    return bind


@pytest.fixture(params=[TCP, UNIX])
def bind_endpoint(request, tmp_path) -> Endpoint:
    if request.param == TCP:
        return Endpoint(TCP, "127.0.0.1", 0)
    return Endpoint(UNIX, str(tmp_path / "tsanet.sock"))


def test_request_response_and_event_roundtrip(bind_endpoint):
    listener = listen(bind_endpoint)
    server: dict[str, Connection] = {}

    def serve():
        conn = listener.accept()
        server["conn"] = conn
        request = conn.recv()
        conn.send(Response(id=request.id, status=Status.OK, data={"echo": request.args}))

    worker = threading.Thread(target=serve)
    worker.start()
    try:
        client = dial(_dial_endpoint(listener, bind_endpoint))

        # Controller -> hub request, hub -> controller response (matched by id).
        client.send(Request(id=42, domain="sweep", op="set_center", args={"hz": 433000000}))
        response = client.recv()
        worker.join(timeout=5)

        assert isinstance(response, Response)
        assert response.id == 42
        assert response.status is Status.OK
        assert response.data == {"echo": {"hz": 433000000}}

        # Unsolicited hub -> controller event over the same connection.
        server["conn"].send(Event(subscription_id=1, domain="trace", op="update", data=[1, 2, 3]))
        event = client.recv()
        assert isinstance(event, Event)
        assert event.data == [1, 2, 3]

        client.close()
        server["conn"].close()
    finally:
        listener.close()


def test_recv_raises_when_peer_closes(bind_endpoint):
    listener = listen(bind_endpoint)

    def serve():
        conn = listener.accept()
        conn.close()

    worker = threading.Thread(target=serve)
    worker.start()
    try:
        client = dial(_dial_endpoint(listener, bind_endpoint))
        with pytest.raises(ConnectionClosed):
            client.recv()
        client.close()
        worker.join(timeout=5)
    finally:
        listener.close()


def test_recv_raises_connection_closed_on_abrupt_reset(bind_endpoint):
    """A peer that vanishes abruptly (crash, kill -9, network drop) sends a
    TCP RST instead of a clean FIN: recv() raises ConnectionResetError
    directly rather than returning b"". This must still surface as the same
    ConnectionClosed callers already handle, not an unhandled OSError.

    SO_LINGER with a zero timeout forces the OS to send a real RST on
    close(), reproducing the reported bug exactly rather than simulating it.
    """
    if bind_endpoint.transport != TCP:
        pytest.skip("SO_LINGER-forced RST is a TCP-specific technique")

    listener = listen(bind_endpoint)

    def serve():
        conn = listener.accept()
        conn._sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        conn._sock.close()

    worker = threading.Thread(target=serve)
    worker.start()
    try:
        client = dial(_dial_endpoint(listener, bind_endpoint))
        worker.join(timeout=5)
        with pytest.raises(ConnectionClosed):
            client.recv()
        client.close()
    finally:
        listener.close()


def test_send_raises_connection_closed_when_peer_is_gone(bind_endpoint):
    """sendall() to a dead peer raises BrokenPipeError/ConnectionResetError
    (an OSError) directly; this must normalize to ConnectionClosed too, so
    callers only need to handle one "the peer is gone" exception."""
    listener = listen(bind_endpoint)

    def serve():
        conn = listener.accept()
        conn.close()

    worker = threading.Thread(target=serve)
    worker.start()
    try:
        client = dial(_dial_endpoint(listener, bind_endpoint))
        worker.join(timeout=5)
        # The peer's close() may not be observed until we actually try to
        # use the socket; send repeatedly until the OS reports it as dead.
        with pytest.raises(ConnectionClosed):
            for _ in range(50):
                client.send(Request(id=1, domain="session", op="status"))
        client.close()
    finally:
        listener.close()


def test_recv_timeout_is_not_mistaken_for_connection_closed(bind_endpoint):
    """Regression: RpcClient sets a receive timeout (rpc_client.py's
    sock.settimeout(_RECV_TIMEOUT)) specifically so its reader loop can wake
    up periodically while idle, and its own "except socket.timeout: continue"
    already treats that as routine, not a disconnect. TimeoutError is an
    OSError subclass, so recv() must not fold it into ConnectionClosed --
    that would tear down a perfectly healthy, merely idle connection on
    every timeout, exactly as reported against a live GUI session.
    """
    listener = listen(bind_endpoint)
    accepted = threading.Event()

    def serve():
        conn = listener.accept()
        accepted.set()
        # Hold the connection open and silent -- never send anything -- so
        # the client's recv() has nothing to read and must time out.
        threading.Event().wait(2.0)
        conn.close()

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    try:
        client = dial(_dial_endpoint(listener, bind_endpoint))
        assert accepted.wait(timeout=5)
        client._sock.settimeout(0.05)

        with pytest.raises(TimeoutError):
            client.recv()

        client.close()
    finally:
        listener.close()


def test_send_timeout_is_not_mistaken_for_connection_closed(bind_endpoint):
    """Same normalization gap as recv(), for the write side.

    Shrinks the accepted socket's receive buffer and never reads from it, so
    the client's sendall() of an oversized payload reliably blocks until its
    own short timeout fires, rather than depending on OS buffering luck.
    """
    listener = listen(bind_endpoint)
    accepted = threading.Event()

    def serve():
        conn = listener.accept()
        conn._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        accepted.set()
        threading.Event().wait(2.0)  # never read -- let the client's buffer fill
        conn.close()

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    try:
        client = dial(_dial_endpoint(listener, bind_endpoint))
        assert accepted.wait(timeout=5)
        client._sock.settimeout(0.2)

        big_request = Request(
            id=1, domain="session", op="status", args={"padding": "x" * 5_000_000}
        )
        with pytest.raises(TimeoutError):
            client.send(big_request)

        client.close()
    finally:
        listener.close()


def test_tcp_endpoint_requires_port():
    with pytest.raises(ValueError):
        Endpoint(TCP, "127.0.0.1")


def test_unknown_transport_rejected():
    with pytest.raises(ValueError):
        Endpoint("serial", "127.0.0.1", 1)


def test_is_loopback():
    assert is_loopback("127.0.0.1")
    assert is_loopback("localhost")
    assert is_loopback("::1")
    assert not is_loopback("0.0.0.0")
    assert not is_loopback("192.168.1.10")


def test_nullsecurity_passthrough():
    sentinel = object()
    assert NullSecurity().wrap(sentinel, server=True) is sentinel


def test_nullsecurity_warns_on_non_loopback(caplog):
    with caplog.at_level(logging.WARNING, logger="tsanet.protocol"):
        NullSecurity().warn_if_insecure(TCP, "0.0.0.0")
    assert any("unencrypted" in record.message for record in caplog.records)


def test_nullsecurity_quiet_on_loopback_and_unix(caplog):
    with caplog.at_level(logging.WARNING, logger="tsanet.protocol"):
        NullSecurity().warn_if_insecure(TCP, "127.0.0.1")
        NullSecurity().warn_if_insecure(UNIX, "/tmp/tsanet.sock")
    assert caplog.records == []
