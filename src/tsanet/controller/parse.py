"""Parse frequency and time values from CLI arguments (brief 9, tsactl conventions).

Supports suffix notation: ``1.5ghz``, ``250k``, ``100mhz``, ``2.4g``,
``1.5s``, ``250ms``, ``100us``.  Returns integer hertz or microseconds.
"""

from __future__ import annotations

import re

# Frequency suffixes: value in hertz.
_FREQ_SUFFIXES: dict[str, int] = {
    "ghz": 1_000_000_000,
    "mhz": 1_000_000,
    "khz": 1_000,
    "hz": 1,
    "g": 1_000_000_000,
    "m": 1_000_000,
    "k": 1_000,
}

# Time suffixes: value in microseconds.
_TIME_SUFFIXES: dict[str, int] = {
    "s": 1_000_000,
    "ms": 1_000,
    "us": 1,
}

_FREQ_RE = re.compile(
    r"^(?P<value>[\d.]+)\s*(?P<suffix>"
    + "|".join(re.escape(s) for s in sorted(_FREQ_SUFFIXES, key=len, reverse=True))
    + r")?$",
    re.IGNORECASE,
)

_TIME_RE = re.compile(
    r"^(?P<value>[\d.]+)\s*(?P<suffix>"
    + "|".join(re.escape(s) for s in sorted(_TIME_SUFFIXES, key=len, reverse=True))
    + r")?$",
    re.IGNORECASE,
)


def parse_frequency(raw: str) -> int:
    """Parse a frequency string like ``1.5ghz`` or ``250k`` into integer hertz.

    Raises :class:`ValueError` if the string cannot be parsed.
    """
    m = _FREQ_RE.match(raw.strip())
    if not m:
        raise ValueError(f"invalid frequency: {raw!r}")
    value = float(m.group("value"))
    suffix = (m.group("suffix") or "hz").lower()
    return round(value * _FREQ_SUFFIXES[suffix])


def parse_time(raw: str) -> int:
    """Parse a time string like ``1.5s`` or ``250ms`` into integer microseconds.

    Raises :class:`ValueError` if the string cannot be parsed.
    """
    m = _TIME_RE.match(raw.strip())
    if not m:
        raise ValueError(f"invalid time: {raw!r}")
    value = float(m.group("value"))
    suffix = (m.group("suffix") or "us").lower()
    return round(value * _TIME_SUFFIXES[suffix])
