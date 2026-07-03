"""Tests for TinySA.read_scanraw, the opt-in tight-poll scanraw fast path.

Constructs a TinySA via the normal legacy-transport constructor path (to
satisfy __init__), then overrides ._tsa/._legacy directly to exercise the
tsapython-backed fast-read branch against a fake serial port -- mirroring
how hub/scanraw_subscription.py reaches into ._tsa today.
"""

from __future__ import annotations

import pytest

from tsanet.device.adapter import TinySA
from fakeserial import FakeSerial


class _FakeTsapython:
    """Stands in for tsapython.tinySA: exposes .ser and a scan_raw fallback."""

    def __init__(self, ser, fallback_frame: bytes = b"{" + b"\x00" * 9 + b"}"):
        self.ser = ser
        self._fallback_frame = fallback_frame
        self.scan_raw_calls = 0

    def scan_raw(self, start, stop, pts):
        self.scan_raw_calls += 1
        return self._fallback_frame


def _fast_path_adapter(ser, fallback_frame: bytes | None = None) -> tuple[TinySA, _FakeTsapython]:
    tx = TinySA(FakeSerial([]))  # legacy constructor path, then swap in tsapython
    fake_tsa = _FakeTsapython(ser, fallback_frame) if fallback_frame else _FakeTsapython(ser)
    tx._tsa = fake_tsa
    tx._legacy = None
    return tx, fake_tsa


def _framed_response(echo: str, pts: int, fill: int = 0) -> bytes:
    """Build a realistic scanraw wire response: echo + '{' + 3*pts bytes + '}'."""
    data = bytes([ord("x"), fill & 0xFF, (fill >> 8) & 0xFF]) * pts
    return echo.encode("ascii") + b"\r\n{" + data + b"}"


class TestFastPath:
    def test_returns_frame_matching_get_binary_return_contract(self):
        pts = 3
        response = _framed_response("scanraw 100 200 3 1", pts, fill=0x1234)
        ser = FakeSerial([response])
        tx, fake_tsa = _fast_path_adapter(ser)

        result = tx.read_scanraw(100, 200, pts)

        assert result[:1] == b"{"
        assert len(result) == 1 + 3 * pts  # '{' + data, trailing '}' dropped
        assert fake_tsa.scan_raw_calls == 0  # fast path succeeded, no fallback

    def test_writes_the_scanraw_command(self):
        pts = 2
        response = _framed_response("scanraw 100 200 2 1", pts)
        ser = FakeSerial([response])
        tx, _ = _fast_path_adapter(ser)

        tx.read_scanraw(100, 200, pts)

        assert ser.written == [b"scanraw 100 200 2 1\r\n"]

    def test_decodes_identically_to_the_existing_struct_unpack_contract(self):
        # Matches hub/scanraw_subscription.py's own decode: data = raw[1:],
        # struct.unpack("<" + "xH"*pts, data).
        import struct

        pts = 4
        values = [100, 200, 300, 400]
        data = b"".join(struct.pack("<xH", v) for v in values)
        response = b"scanraw 0 1000 4 1\r\n{" + data + b"}"
        ser = FakeSerial([response])
        tx, _ = _fast_path_adapter(ser)

        result = tx.read_scanraw(0, 1000, pts)

        decoded = struct.unpack("<" + "xH" * pts, result[1:])
        assert list(decoded) == values


class TestFallback:
    def test_falls_back_to_scan_raw_when_ser_attribute_missing(self):
        tx = TinySA(FakeSerial([]))
        fallback_frame = b"{fallback-data}"

        class _NoSerTsapython:
            def __init__(self):
                self.scan_raw_calls = 0

            def scan_raw(self, start, stop, pts):
                self.scan_raw_calls += 1
                return fallback_frame

        fake_tsa = _NoSerTsapython()
        tx._tsa = fake_tsa
        tx._legacy = None

        result = tx.read_scanraw(0, 100, 1)

        assert result == fallback_frame
        assert fake_tsa.scan_raw_calls == 1

    def test_falls_back_to_scan_raw_on_timeout(self):
        # No response ever loaded -> ser.read() always returns b"", forcing
        # the deadline path. Uses a near-zero timeout to keep the test fast.
        ser = FakeSerial([])
        tx, fake_tsa = _fast_path_adapter(ser)

        result = tx.read_scanraw(0, 100, 1, timeout=0.01)

        assert result == fake_tsa._fallback_frame
        assert fake_tsa.scan_raw_calls == 1

    def test_falls_back_on_short_frame(self):
        # Frame start '{' present but not enough bytes follow before the
        # buffer runs dry -- must fall back rather than return a short read.
        pts = 5
        truncated = b"scanraw 0 100 5 1\r\n{" + b"\x00" * 3  # far short of 3*pts
        ser = FakeSerial([truncated])
        tx, fake_tsa = _fast_path_adapter(ser)

        result = tx.read_scanraw(0, 100, pts, timeout=0.01)

        assert result == fake_tsa._fallback_frame
        assert fake_tsa.scan_raw_calls == 1


class TestLegacyTransport:
    def test_raises_not_implemented_over_legacy_transport(self):
        tx = TinySA(FakeSerial([]))  # stays on the legacy path
        with pytest.raises(NotImplementedError):
            tx.read_scanraw(0, 100, 10)
