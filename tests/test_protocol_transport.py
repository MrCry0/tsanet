"""Loopback tests for listen/dial over tcp and unix, in both directions."""

from __future__ import annotations

import logging
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
