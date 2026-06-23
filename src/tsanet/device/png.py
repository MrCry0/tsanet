"""Minimal PNG encoder for decoded framebuffers (brief 6.1).

The hub PNG-encodes the decoded RGBA framebuffer before sending it to the
controller. This uses only the standard library (``zlib``), so no image
dependency is added to the hub install.
"""

from __future__ import annotations

import struct
import zlib

_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def encode_png(rgba: bytes, width: int, height: int) -> bytes:
    """Encode packed RGBA8888 bytes as an 8-bit RGBA PNG."""
    if len(rgba) != width * height * 4:
        raise ValueError(f"expected {width * height * 4} RGBA bytes, got {len(rgba)}")

    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0 (none) per scanline
        raw.extend(rgba[y * stride : (y + 1) * stride])

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw))
    return _SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")
