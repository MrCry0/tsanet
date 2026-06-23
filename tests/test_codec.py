"""Tests for frame encoding/decoding and message schemas."""

from __future__ import annotations

import msgpack
import pytest

from tsanet.common.errors import FrameError
from tsanet.protocol.codec import (
    HEADER_SIZE,
    MAX_FRAME_SIZE,
    decode_length,
    decode_payload,
    encode,
)
from tsanet.protocol.messages import Event, Request, Response, Status


def roundtrip(message):
    frame = encode(message)
    length = decode_length(frame[:HEADER_SIZE])
    assert length == len(frame) - HEADER_SIZE
    return decode_payload(frame[HEADER_SIZE:])


def test_request_roundtrip():
    msg = Request(id=1, domain="sweep", op="set_center", args={"hz": 433000000})
    assert roundtrip(msg) == msg


def test_response_ok_roundtrip():
    msg = Response(id=2, status=Status.OK, data={"frequencies": [1, 2, 3]})
    assert roundtrip(msg) == msg


def test_response_error_roundtrip():
    msg = Response(id=3, status=Status.ERROR, error="device timeout")
    assert roundtrip(msg) == msg


def test_event_roundtrip_with_binary_data():
    msg = Event(subscription_id=7, domain="trace", op="update", data=b"\x00\xff\x10")
    decoded = roundtrip(msg)
    assert decoded == msg
    assert isinstance(decoded.data, bytes)


def test_decode_rejects_unknown_type():
    payload = msgpack.packb({"type": "bogus"}, use_bin_type=True)
    with pytest.raises(FrameError):
        decode_payload(payload)


def test_decode_rejects_missing_field():
    payload = msgpack.packb({"type": "request", "id": 1}, use_bin_type=True)
    with pytest.raises(FrameError):
        decode_payload(payload)


def test_decode_rejects_non_map():
    payload = msgpack.packb([1, 2, 3], use_bin_type=True)
    with pytest.raises(FrameError):
        decode_payload(payload)


def test_decode_length_rejects_oversize():
    header = (MAX_FRAME_SIZE + 1).to_bytes(HEADER_SIZE, "big")
    with pytest.raises(FrameError):
        decode_length(header)


def test_decode_length_rejects_short_header():
    with pytest.raises(FrameError):
        decode_length(b"\x00\x00")
