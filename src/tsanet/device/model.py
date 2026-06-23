"""tinySA model identification and per-model constants.

The version probe and its parsing regex are ported from
``go-tinysa/device_probe.go`` (see brief section 2.4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from tsanet.common.errors import ProtocolError


class Model(Enum):
    """Known tinySA models.

    The basic model is recognized but otherwise out of scope; only the data
    model accommodates it so support is not precluded later (brief 2.4).
    """

    ULTRA = "tinySA4"
    BASIC = "tinySA"


#: Framebuffer dimensions (width, height) in pixels, per model. Used to size
#: the raw RGB565 ``capture`` payload (brief 2.4 / 4).
FRAMEBUFFER: dict[Model, tuple[int, int]] = {
    Model.ULTRA: (480, 320),
    Model.BASIC: (320, 280),
}

#: Valid ``calc <id> <type>`` trace calculation types (brief 4).
VALID_CALC = frozenset({"off", "minh", "maxh", "maxd", "aver4", "aver16", "aver", "quasi"})

#: Valid ``trace <unit>`` units (brief 4).
VALID_UNITS = frozenset({"RAW", "dBm", "dBmV", "dBuV", "V", "Vpp", "W"})

# Group 1: model string, group 2: firmware version, group 3: hardware version.
_VERSION_RE = re.compile(r"^(tinySA\w+)_v?(\S+)?\s*HW Version:V(.*?)\s*$")


@dataclass(frozen=True)
class DeviceInfo:
    """Identity extracted from a ``version`` response."""

    model_string: str
    model: Model
    firmware: str | None
    hardware: str


def parse_version(text: str) -> DeviceInfo:
    """Parse a ``version`` response into a :class:`DeviceInfo`.

    Raises :class:`ProtocolError` if no line matches the expected format.
    """
    for candidate in (text.strip(), *text.splitlines()):
        match = _VERSION_RE.match(candidate.strip())
        if match:
            model_string = match.group(1)
            model = Model.ULTRA if model_string == Model.ULTRA.value else Model.BASIC
            return DeviceInfo(
                model_string=model_string,
                model=model,
                firmware=match.group(2),
                hardware=match.group(3),
            )
    raise ProtocolError(f"unrecognized version response: {text!r}")
