"""Tests for the low-level serial framing: echo-strip, prompt-detect, retry."""

from __future__ import annotations

import pytest

from tsanet.common.errors import DeviceTimeout, ProtocolError
from tsanet.device.transport import TinySA


def test_send_strips_echo_and_prompt(fake_serial):
    port = fake_serial([b"version\r\ntinySA4_v1.4\r\nch> "])
    tx = TinySA(port)

    assert tx.send("version") == "tinySA4_v1.4"
    assert port.written == [b"version\r"]


def test_send_preserves_internal_newlines(fake_serial):
    port = fake_serial([b"marker\r\n1 433000000\r\n2 868000000\r\nch> "])
    tx = TinySA(port)

    assert tx.send("marker") == "1 433000000\r\n2 868000000"


def test_send_empty_response(fake_serial):
    port = fake_serial([b"pause\r\nch> "])
    tx = TinySA(port)

    assert tx.send("pause") == ""


def test_send_retries_on_timeout_then_succeeds(fake_serial):
    # First write yields no prompt (timeout), second write yields a full frame.
    port = fake_serial([b"garbage with no prompt", b"version\r\ntinySA4\r\nch> "])
    tx = TinySA(port, attempts=3)

    assert tx.send("version") == "tinySA4"
    assert port.written == [b"version\r", b"version\r"]


def test_send_raises_after_exhausting_attempts(fake_serial):
    port = fake_serial([b"", b"", b""])
    tx = TinySA(port, attempts=3)

    with pytest.raises(DeviceTimeout):
        tx.send("version")
    assert len(port.written) == 3


def test_send_binary_returns_exact_payload(fake_serial):
    payload = bytes(range(8))
    port = fake_serial([b"capture\r\n" + payload + b"ch> "])
    tx = TinySA(port)

    assert tx.send_binary("capture", len(payload)) == payload
    assert port.written == [b"capture\r"]


def test_send_binary_payload_may_contain_prompt_bytes(fake_serial):
    payload = b"abch> ef"  # contains the prompt sequence mid-stream
    port = fake_serial([b"capture\r\n" + payload + b"ch> "])
    tx = TinySA(port)

    assert tx.send_binary("capture", len(payload)) == payload


def test_send_binary_missing_trailing_prompt(fake_serial):
    payload = bytes(4)
    port = fake_serial([b"capture\r\n" + payload + b"XXXX"])
    tx = TinySA(port)

    with pytest.raises(ProtocolError):
        tx.send_binary("capture", len(payload))


def test_send_binary_short_payload_times_out(fake_serial):
    port = fake_serial([b"capture\r\n\x01\x02"])  # only 2 of 4 bytes
    tx = TinySA(port, attempts=1)

    with pytest.raises(DeviceTimeout):
        tx.send_binary("capture", 4)


def test_write_only_sends_without_reading(fake_serial):
    port = fake_serial([])
    tx = TinySA(port)

    tx.write_only("reset")
    assert port.written == [b"reset\r"]


def test_attempts_must_be_positive(fake_serial):
    with pytest.raises(ValueError):
        TinySA(fake_serial([]), attempts=0)
