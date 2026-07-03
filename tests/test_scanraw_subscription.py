"""Tests for ScanrawSubscription's fast_read flag routing.

read_scanraw() itself is unit-tested in test_adapter_scanraw.py; this only
checks that ScanrawSubscription._run() calls the right method for the flag.
"""

from __future__ import annotations

import struct

from tsanet.hub.scanraw_subscription import ScanrawSubscription


class _FakeTsapython:
    def __init__(self, stop_event):
        self.scan_raw_calls = 0
        self._stop_event = stop_event

    def scan_raw(self, start, stop, pts):
        self.scan_raw_calls += 1
        self._stop_event.set()  # exit the _run loop after this one iteration
        return _frame(pts)


class _FakeTx:
    def __init__(self, stop_event):
        self._tsa = _FakeTsapython(stop_event)
        self.read_scanraw_calls = 0
        self._stop_event = stop_event

    def read_scanraw(self, start, stop, pts):
        self.read_scanraw_calls += 1
        self._stop_event.set()
        return _frame(pts)


class _FakeConnection:
    def __init__(self):
        self.sent = []

    def send(self, event):
        self.sent.append(event)


def _frame(pts: int) -> bytes:
    data = b"".join(struct.pack("<xH", 0) for _ in range(pts))
    return b"{" + data + b"}"


def _make_subscription(tx, fast_read: bool) -> ScanrawSubscription:
    return ScanrawSubscription(
        tx,
        _FakeConnection(),
        start_hz=0,
        stop_hz=1000,
        pts=2,
        interval=None,
        subscription_id=1,
        fast_read=fast_read,
    )


def test_fast_read_true_calls_read_scanraw_not_scan_raw():
    sub = _make_subscription(None, fast_read=True)
    tx = _FakeTx(sub._stop_event)
    sub._tx = tx

    sub._run()

    assert tx.read_scanraw_calls == 1
    assert tx._tsa.scan_raw_calls == 0


def test_fast_read_false_calls_scan_raw_not_read_scanraw():
    sub = _make_subscription(None, fast_read=False)
    tx = _FakeTx(sub._stop_event)
    sub._tx = tx

    sub._run()

    assert tx._tsa.scan_raw_calls == 1
    assert tx.read_scanraw_calls == 0


def test_fast_read_defaults_to_false():
    tx = _FakeTx.__new__(_FakeTx)  # avoid needing a stop_event up front
    sub = ScanrawSubscription(
        tx,
        _FakeConnection(),
        start_hz=0,
        stop_hz=1000,
        pts=2,
        interval=None,
        subscription_id=1,
    )
    assert sub._fast_read is False
