"""Tests for the live-graph subscription push loop."""

from __future__ import annotations

import threading
import time

from fakeserial import FakeDevicePort, FakeSerial

from tsanet.common.errors import DispatchError, SessionError
from tsanet.device.transport import TinySA
from tsanet.hub.registry import DeviceRegistry
from tsanet.hub.session import SessionManager
from tsanet.hub.subscriptions import SubscriptionManager
from tsanet.protocol.messages import Event


class RecordingConnection:
    """Accepts :meth:`send` calls and records every event."""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self.closed = False
        self._lock = threading.Lock()

    def send(self, message: Event) -> None:
        with self._lock:
            self.events.append(message)

    def close(self) -> None:
        self.closed = True


class _FakeOpener:
    def __init__(self, devices: dict[str, bytes | None]) -> None:
        self._devices = devices

    def __call__(self, name: str) -> FakeDevicePort:
        return FakeDevicePort(body=self._devices[name])


FREQS_RESP = b"frequencies\r\n100000000\r\n200000000\r\nch> "
TRACE1_RESP = b"trace 1 value\r\n-50.5\r\n-51.2\r\nch> "
TRACE2_RESP = b"trace 2 value\r\n-60.0\r\n-61.5\r\nch> "


def _setup():
    opener = _FakeOpener({"/dev/ultra": b"tinySA4_v1.4 HW Version:V0.4.5.1"})
    registry = DeviceRegistry(lambda: ["/dev/ultra"], opener, probe_attempts=1)
    registry.scan()

    sessions = SessionManager()
    conn = RecordingConnection()
    sessions.admit(conn, peer="test")
    sessions.select_device("/dev/ultra")

    mgr = SubscriptionManager(registry, sessions)
    return mgr, registry, sessions, conn


def _wait_for_events(conn, count, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with conn._lock:
            if len(conn.events) >= count:
                return conn.events[:]
        time.sleep(0.01)
    return conn.events[:]


# -- basic subscribe / unsubscribe ----------------------------------------


def test_subscribe_pushes_events():
    mgr, registry, _, conn = _setup()
    tx = FakeSerial([FREQS_RESP, TRACE1_RESP, FREQS_RESP])
    _replace(registry, "/dev/ultra", TinySA(tx, attempts=1))

    mgr.subscribe(ids=[1], interval=None)
    events = _wait_for_events(conn, 2)  # initial freqs + first trace update
    mgr.unsubscribe()

    assert len(events) >= 1
    assert events[0].domain == "trace"
    assert events[0].op == "update"


def test_unsubscribe_stops_events():
    mgr, registry, _, conn = _setup()
    tx = FakeSerial([FREQS_RESP])
    _replace(registry, "/dev/ultra", TinySA(tx, attempts=1))

    mgr.subscribe(ids=[1], interval=None)
    mgr.unsubscribe()
    time.sleep(0.05)

    # Should have at most the initial frequency event; no further events.
    assert len(conn.events) <= 1


def test_subscribe_replace_previous():
    mgr, registry, _, conn = _setup()
    tx = FakeSerial([FREQS_RESP, FREQS_RESP])
    _replace(registry, "/dev/ultra", TinySA(tx, attempts=1))

    mgr.subscribe(ids=[1], interval=None)
    mgr.subscribe(ids=[2], interval=None)
    mgr.unsubscribe()

    # The second subscribe cancels the first; both are eventually stopped.
    assert len(conn.events) <= 3


# -- error cases -----------------------------------------------------------


def test_subscribe_no_session():
    registry = DeviceRegistry(lambda: [], lambda n: FakeDevicePort())
    mgr = SubscriptionManager(registry, SessionManager())
    with _expect(SessionError, "no active session"):
        mgr.subscribe(ids=[1], interval=None)


def test_subscribe_no_device_selected():
    opener = _FakeOpener({"/dev/ultra": b"tinySA4_v1.4 HW Version:V0.4.5.1"})
    registry = DeviceRegistry(lambda: ["/dev/ultra"], opener, probe_attempts=1)
    registry.scan()
    sessions = SessionManager()
    sessions.admit(RecordingConnection())
    mgr = SubscriptionManager(registry, sessions)
    with _expect(DispatchError, "no device selected"):
        mgr.subscribe(ids=[1], interval=None)


def test_unsubscribe_when_nothing_active():
    mgr, *_ = _setup()
    result = mgr.unsubscribe()
    assert result == {"active": False}


# -- event data structure --------------------------------------------------


def test_event_has_initial_frequencies():
    mgr, registry, _, conn = _setup()
    tx = FakeSerial([FREQS_RESP])
    _replace(registry, "/dev/ultra", TinySA(tx, attempts=1))

    mgr.subscribe(ids=[1], interval=None)
    events = _wait_for_events(conn, 1)
    mgr.unsubscribe()

    assert len(events) >= 1
    freq_event = events[0]
    assert freq_event.data["frequencies"] == [100000000, 200000000]
    assert freq_event.data["traces"] == {}


def test_event_has_trace_values():
    mgr, registry, _, conn = _setup()
    tx = FakeSerial([FREQS_RESP, TRACE1_RESP, TRACE2_RESP, FREQS_RESP])
    _replace(registry, "/dev/ultra", TinySA(tx, attempts=1))

    mgr.subscribe(ids=[1, 2], interval=None)
    events = _wait_for_events(conn, 2)  # initial freq event + first update
    mgr.unsubscribe()

    assert len(events) >= 2
    update = events[1]
    assert "1" in update.data["traces"]
    assert "2" in update.data["traces"]
    assert update.data["traces"]["1"] == [-50.5, -51.2]
    assert update.data["traces"]["2"] == [-60.0, -61.5]


def test_frequencies_only_resent_when_changed():
    mgr, registry, _, conn = _setup()
    tx = FakeSerial(
        [
            FREQS_RESP,  # initial frequencies
            TRACE1_RESP,
            FREQS_RESP,  # cycle 1: same freqs
            TRACE1_RESP,
            FREQS_RESP,  # cycle 2: same freqs
            TRACE1_RESP,
            b"frequencies\r\n300000000\r\nch> ",  # cycle 3: changed
        ]
    )
    _replace(registry, "/dev/ultra", TinySA(tx, attempts=1))

    mgr.subscribe(ids=[1], interval=None)
    events = _wait_for_events(conn, 4, timeout=3.0)  # init + 3 cycles
    mgr.unsubscribe()

    assert len(events) >= 3

    # First event always includes frequencies.
    assert "frequencies" in events[0].data

    # Subsequent events should not include frequencies unless changed.
    # The change comes on the third post-init event (index 3 if channels match).
    freq_in_updates = [e for e in events[1:] if "frequencies" in e.data]
    assert len(freq_in_updates) == 1  # only the changed one


# -- interval pacing -------------------------------------------------------


def test_subscribe_with_interval_paces():
    mgr, registry, _, conn = _setup()
    tx = FakeSerial(
        [
            FREQS_RESP,
            TRACE1_RESP,
            FREQS_RESP,  # cycle 1
            TRACE1_RESP,
            FREQS_RESP,  # cycle 2
        ]
    )
    _replace(registry, "/dev/ultra", TinySA(tx, attempts=1))

    start = time.monotonic()
    mgr.subscribe(ids=[1], interval=0.1)
    _wait_for_events(conn, 3, timeout=2.0)
    elapsed = time.monotonic() - start
    mgr.unsubscribe()

    # Initial event is pushed before the first sleep, then cycles sleep
    # for interval seconds.  At least one full interval should have elapsed
    # by the time 3 events arrive.
    assert elapsed >= 0.08
    assert len(conn.events) >= 3


# -- shutdown --------------------------------------------------------------


def test_shutdown_stops_active_subscription():
    mgr, registry, _, conn = _setup()
    tx = FakeSerial([FREQS_RESP])
    _replace(registry, "/dev/ultra", TinySA(tx, attempts=1))

    mgr.subscribe(ids=[1], interval=None)
    _wait_for_events(conn, 1)

    assert mgr.active() is True
    mgr.shutdown()
    assert mgr.active() is False


# -- dispatcher integration ------------------------------------------------


def test_dispatcher_subscribe_and_unsubscribe():
    from tsanet.hub.dispatcher import Dispatcher
    from tsanet.protocol.messages import Request, Status

    mgr, registry, sessions, conn = _setup()
    tx = FakeSerial([FREQS_RESP])
    _replace(registry, "/dev/ultra", TinySA(tx, attempts=1))
    dispatcher = Dispatcher(registry, sessions, subscriptions=mgr)

    # Subscribe
    req = Request(id=1, domain="trace", op="subscribe", args={"ids": [1], "interval": None})
    resp = dispatcher.dispatch(req, conn)
    assert resp.status == Status.OK
    assert resp.data["active"] is True
    assert "subscription_id" in resp.data

    # Unsubscribe
    req2 = Request(id=2, domain="trace", op="unsubscribe", args={})
    resp2 = dispatcher.dispatch(req2, conn)
    assert resp2.status == Status.OK
    assert resp2.data == {"active": False}


def test_dispatcher_subscribe_without_manager_returns_error():
    from tsanet.hub.dispatcher import Dispatcher
    from tsanet.protocol.messages import Request, Status

    mgr, registry, sessions, conn = _setup()
    dispatcher = Dispatcher(registry, sessions, subscriptions=None)

    req = Request(id=1, domain="trace", op="subscribe", args={"ids": [1]})
    resp = dispatcher.dispatch(req, conn)
    assert resp.status == Status.ERROR
    assert "not configured" in resp.error.lower()


# -- helpers ---------------------------------------------------------------


def _replace(registry, device_id, tx):
    registry.get(device_id).transport = tx


class _ExpectContext:
    def __init__(self, exc_type, fragment=""):
        self._exc_type = exc_type
        self._fragment = fragment.lower()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError(f"expected {self._exc_type.__name__}, no exception raised")
        if not issubclass(exc_type, self._exc_type):
            return False
        if self._fragment and self._fragment not in str(exc).lower():
            raise AssertionError(f"message {exc!r} did not contain {self._fragment!r}")
        return True


def _expect(exc_type, fragment=""):
    return _ExpectContext(exc_type, fragment)
