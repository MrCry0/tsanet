"""Capture command (brief 4: Capture, 6.1).

``capture`` returns a raw big-endian RGB565 framebuffer sized by the model.
This returns the raw bytes; decoding and PNG encoding happen on the hub.
"""

from __future__ import annotations

from tsanet.device.model import FRAMEBUFFER, Model
from tsanet.device.transport import TinySA


def fetch_framebuffer(tx: TinySA, model: Model) -> bytes:
    """Fetch the raw RGB565 framebuffer for the given model."""
    width, height = FRAMEBUFFER[model]
    return tx.send_binary("capture", width * height * 2)
