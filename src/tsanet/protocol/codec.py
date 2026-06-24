"""Frame encoding/decoding (brief 3.1).

Each frame is a 4-byte big-endian length prefix followed by a MessagePack
payload. MessagePack rather than JSON so binary payloads (PNG screenshots,
raw scan dumps) ride natively as bytes without base64 inflation.
"""

from __future__ import annotations

import msgpack

from tsanet.common.errors import FrameError
from tsanet.protocol.messages import Message, message_from_dict

#: Length prefix size in bytes.
HEADER_SIZE = 4

#: Largest payload accepted, to bound allocation on a hostile or corrupt frame.
MAX_FRAME_SIZE = 64 * 1024 * 1024


def encode(message: Message) -> bytes:
    """Encode a message into a length-prefixed MessagePack frame."""
    payload = msgpack.packb(message.to_dict(), use_bin_type=True)
    if len(payload) > MAX_FRAME_SIZE:
        raise FrameError(f"frame of {len(payload)} bytes exceeds {MAX_FRAME_SIZE}")
    return len(payload).to_bytes(HEADER_SIZE, "big") + payload


def decode_length(header: bytes) -> int:
    """Decode a 4-byte length prefix, validating it against the size limit."""
    if len(header) != HEADER_SIZE:
        raise FrameError(f"length header must be {HEADER_SIZE} bytes, got {len(header)}")
    length = int.from_bytes(header, "big")
    if length > MAX_FRAME_SIZE:
        raise FrameError(f"declared frame size {length} exceeds {MAX_FRAME_SIZE}")
    return length


def decode_payload(payload: bytes) -> Message:
    """Decode a MessagePack payload into a message."""
    try:
        obj = msgpack.unpackb(payload, raw=False, strict_map_key=False)
    except (ValueError, msgpack.UnpackException) as error:
        raise FrameError(f"invalid MessagePack payload: {error}") from error
    return message_from_dict(obj)
