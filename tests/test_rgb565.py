"""Tests for RGB565 -> RGBA decoding."""

from __future__ import annotations

import pytest

from tsanet.device.rgb565 import decode_rgb565


def test_decode_primary_colors():
    # 0xF800 = red, 0x07E0 = green, 0x001F = blue (big-endian byte pairs).
    data = bytes([0xF8, 0x00, 0x07, 0xE0, 0x00, 0x1F])
    out = decode_rgb565(data, width=3, height=1)

    assert out == bytes(
        [
            255,
            0,
            0,
            255,  # red
            0,
            255,
            0,
            255,  # green
            0,
            0,
            255,
            255,  # blue
        ]
    )


def test_decode_black_and_white():
    data = bytes([0x00, 0x00, 0xFF, 0xFF])
    out = decode_rgb565(data, width=2, height=1)

    assert out == bytes([0, 0, 0, 255, 255, 255, 255, 255])


def test_decode_rejects_wrong_size():
    with pytest.raises(ValueError):
        decode_rgb565(b"\x00\x00", width=2, height=1)
