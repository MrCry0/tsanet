"""Regression test: calling RpcClient.call() from inside an event callback
must not deadlock the reader thread that would deliver its response.

RpcClient.call() blocks on a condition variable that is only notified by
_reader_loop's own thread when it reads the matching response (see
rpc_client.py). Event callbacks are invoked directly from that same
reader thread (_reader_loop calls cb(msg) inline, before looping back to
recv() again). So a call() made from inside an event callback can never
complete: the thread that would deliver the response is the very thread
stuck waiting for it. This is exactly what happened when the GUI's
single-shot capture handler called _stop_stream() -- which calls
RpcClient.call("scanraw", "unsubscribe") -- directly from
_on_scanraw_event() while that event callback still ran on the reader
thread. The fix routes event handling through a Qt signal so it runs on
the GUI thread instead; this test guards the underlying RpcClient
behavior that makes that pattern dangerous in the first place.
"""

from __future__ import annotations

import threading

from tsanet.common.config import NetworkConfig, SecurityConfig
from tsanet.controller.config import ControllerConfig
from tsanet.controller.rpc_client import RpcClient
from tsanet.protocol.messages import Event, Request, Response, Status
from tsanet.protocol.transport import Endpoint, TCP, listen


def _client_config(port):
    return ControllerConfig(
        network=NetworkConfig(mode="dial", transport="tcp", address="127.0.0.1", port=port),
        security=SecurityConfig(),
    )


class _FakeHubPeer:
    """A minimal hand-scripted peer: OKs every request, can push an Event."""

    def __init__(self):
        listener = listen(Endpoint(TCP, "127.0.0.1", 0))
        self.port = listener.port
        self._conn = None
        self._accept_thread = threading.Thread(target=self._accept, args=(listener,), daemon=True)
        self._accept_thread.start()

    def _accept(self, listener):
        self._conn = listener.accept()
        listener.close()
        while True:
            try:
                msg = self._conn.recv()
            except Exception:
                return
            if isinstance(msg, Request):
                self._conn.send(Response(id=msg.id, status=Status.OK, data=None))

    def send_event(self, domain: str, op: str, data: object) -> None:
        while self._conn is None:
            pass
        self._conn.send(Event(subscription_id=1, domain=domain, op=op, data=data))


def test_call_from_within_event_callback_deadlocks():
    """Documents the hazard directly: RpcClient.call() inside an event
    callback never returns, because the reader thread running the
    callback is the same thread that would deliver the call's response."""
    peer = _FakeHubPeer()
    client = RpcClient(_client_config(peer.port))
    client.connect()

    hung = threading.Event()
    finished = threading.Event()

    def on_event(_event):
        client.call("session", "status")  # deadlocks: see module docstring
        finished.set()

    client.on_event(on_event)
    peer.send_event("scanraw", "update", {"level": [1.0]})

    def watchdog():
        if not finished.wait(timeout=2.0):
            hung.set()

    w = threading.Thread(target=watchdog, daemon=True)
    w.start()
    w.join(timeout=3.0)

    assert hung.is_set(), (
        "expected the naive call-from-callback pattern to hang; if this "
        "fails, RpcClient's threading model changed and GUI code calling "
        "RpcClient.call() from an event callback may no longer deadlock "
        "-- but it should still be routed off the reader thread on principle."
    )


def test_deferring_the_call_off_the_reader_thread_avoids_the_deadlock():
    """The fix's shape: doing the call from a different thread (standing in
    for the GUI thread a Qt queued-signal handler would run on) works."""
    peer = _FakeHubPeer()
    client = RpcClient(_client_config(peer.port))
    client.connect()

    finished = threading.Event()

    def on_event(_event):
        # Simulate a signal/slot bridge handing off to another thread
        # instead of calling back into the reader thread's own call().
        def deferred():
            client.call("session", "status")
            finished.set()

        threading.Thread(target=deferred, daemon=True).start()

    client.on_event(on_event)
    peer.send_event("scanraw", "update", {"level": [1.0]})

    assert finished.wait(timeout=3.0), "deferring the call off the reader thread should not hang"
