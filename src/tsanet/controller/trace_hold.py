"""Client-side trace hold computation, shared by the GUI's Spectrum tab.

The hub streams a single raw scan per sweep (scanraw); the device's own
trace calc modes (see device/model.py::VALID_CALC) are approximated here
from that one stream rather than by polling separate device-side trace
channels. This keeps the fast binary stream as the only per-sweep RPC
round trip.

Only the modes with a well-defined, reproducible computation are offered:
live, min/max hold, and fixed-count averages matching the device's own
aver4/aver16 presets (the firmware has no arbitrary-count averaging --
see tsapython's levels_gain.py::calc(), whose accepted values are exactly
off/minh/maxh/maxd/aver4/aver16/quasip). "maxd" and "quasi" are best-effort
approximations, not the certified device algorithms; see their docstrings.
"""

from __future__ import annotations

from collections import deque

VALID_MODES = ("live", "min", "max", "maxd", "avg", "quasi")

#: Max-decay: per-update fallback rate in dB/unit when no new peak is seen.
#: The real firmware's decay rate is not documented; this is a reasonable
#: illustrative default, not a reproduction of device behavior.
MAXD_DECAY_STEP = 1.0

#: Quasi-peak approximation: fast charge toward a rising signal, slow
#: decay otherwise. These are illustrative time constants for a relative,
#: non-certified peak-weighted indicator -- not a CISPR 16-1-1 detector,
#: which requires real elapsed-time-based RC charge/discharge constants
#: that vary by frequency band.
QUASI_CHARGE_ALPHA = 0.7
QUASI_DISCHARGE_ALPHA = 0.05


class TraceHold:
    """Tracks one trace slot's running value across incoming scan frames.

    ``mode`` is one of ``VALID_MODES``. For ``"avg"``, ``window`` is the
    number of most recent frames averaged -- use 4 or 16 to match the
    device's own aver4/aver16 presets.
    """

    def __init__(self, mode: str = "live", window: int = 4) -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"unknown trace hold mode: {mode!r}")
        if window < 1:
            raise ValueError("window must be at least 1")
        self.mode = mode
        self.window = window
        self._held: list[float] | None = None
        self._frames: deque[list[float]] = deque(maxlen=window)

    def reset(self) -> None:
        """Clear accumulated min/max/average state (not the mode itself)."""
        self._held = None
        self._frames.clear()

    def update(self, values) -> list[float]:
        """Feed one new raw scan frame; return the values to plot for this slot."""
        values = list(values)

        if self.mode == "live":
            return values

        if self._held is not None and len(self._held) != len(values):
            self.reset()

        if self.mode == "min":
            if self._held is None:
                self._held = values
            else:
                self._held = [min(a, b) for a, b in zip(self._held, values)]
            return self._held

        if self.mode == "max":
            if self._held is None:
                self._held = values
            else:
                self._held = [max(a, b) for a, b in zip(self._held, values)]
            return self._held

        if self.mode == "maxd":
            if self._held is None:
                self._held = values
            else:
                self._held = [
                    max(new, held - MAXD_DECAY_STEP) for held, new in zip(self._held, values)
                ]
            return self._held

        if self.mode == "quasi":
            if self._held is None:
                self._held = values
            else:
                self._held = [
                    held + QUASI_CHARGE_ALPHA * (new - held)
                    if new >= held
                    else held + QUASI_DISCHARGE_ALPHA * (new - held)
                    for held, new in zip(self._held, values)
                ]
            return self._held

        # avg
        if self._frames and len(self._frames[0]) != len(values):
            self._frames.clear()
        self._frames.append(values)
        n = len(self._frames)
        return [sum(frame[i] for frame in self._frames) / n for i in range(len(values))]
