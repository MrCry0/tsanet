"""Client-side trace hold computation, shared by the GUI's Spectrum tab.

The hub streams a single raw scan per sweep (scanraw); Normal/Min-hold/
Max-hold/Average trace modes -- as seen on the device's own display -- are
computed here from that one stream rather than by polling separate
device-side trace channels. This keeps the fast binary stream as the only
per-sweep RPC round trip.
"""

from __future__ import annotations

from collections import deque

VALID_MODES = ("live", "min", "max", "avg")


class TraceHold:
    """Tracks one trace slot's running value across incoming scan frames.

    ``mode`` is one of ``VALID_MODES``. For ``"avg"``, ``window`` is the
    number of most recent frames averaged (a fixed-count moving average,
    matching the device's own "Trace avg N" convention).
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

        # avg
        if self._frames and len(self._frames[0]) != len(values):
            self._frames.clear()
        self._frames.append(values)
        n = len(self._frames)
        return [sum(frame[i] for frame in self._frames) / n for i in range(len(values))]
