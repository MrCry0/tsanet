"""Client-side marker amplitude lookup, shared by the GUI's Spectrum tab.

During streaming, a marker's amplitude is read from the current scan frame
by nearest-bin lookup instead of a per-frame RPC round trip to the device
-- the same rationale as trace hold computation in trace_hold.py.
"""

from __future__ import annotations

import bisect


def nearest_amplitude(freqs: list[int], level: list[float], target_hz: int) -> float | None:
    """Return the level at the frequency bin closest to ``target_hz``.

    ``freqs`` must be sorted ascending (as scanraw frames always are).
    Returns ``None`` for empty input.
    """
    if not freqs or not level:
        return None
    n = min(len(freqs), len(level))
    i = bisect.bisect_left(freqs, target_hz, hi=n)
    if i <= 0:
        return level[0]
    if i >= n:
        return level[n - 1]
    before, after = freqs[i - 1], freqs[i]
    i = i if (after - target_hz) < (target_hz - before) else i - 1
    return level[i]
