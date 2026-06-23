"""Decode a raw big-endian RGB565 framebuffer to RGBA bytes (brief 4).

The ``capture`` command returns ``width * height * 2`` bytes of big-endian
RGB565 pixels. The device sends raw pixels, not a PNG; PNG encoding happens
later, on the hub.
"""

from __future__ import annotations


def decode_rgb565(data: bytes, width: int, height: int) -> bytes:
    """Convert a big-endian RGB565 framebuffer into packed RGBA8888 bytes.

    Returns ``width * height * 4`` bytes (R, G, B, A per pixel, A always 255).
    Raises :class:`ValueError` if ``data`` is not exactly the expected size.
    """
    pixel_count = width * height
    expected = pixel_count * 2
    if len(data) != expected:
        raise ValueError(f"expected {expected} bytes for {width}x{height}, got {len(data)}")

    out = bytearray(pixel_count * 4)
    for i in range(pixel_count):
        pixel = (data[2 * i] << 8) | data[2 * i + 1]
        r = (pixel >> 11) & 0x1F
        g = (pixel >> 5) & 0x3F
        b = pixel & 0x1F
        out[4 * i] = round(r * 255 / 31)
        out[4 * i + 1] = round(g * 255 / 63)
        out[4 * i + 2] = round(b * 255 / 31)
        out[4 * i + 3] = 255
    return bytes(out)
