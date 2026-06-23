"""Trace statistics over a frequency sub-range (brief 6.4).

Computes average power, median, min@freq, and max@freq from trace data,
with unit-aware linear averaging.  This is a controller-side computation
on top of ``trace.fetch_data`` — no new Hub RPC is needed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class StatsResult:
    average: float
    median: float
    minimum: float
    min_freq: int
    maximum: float
    max_freq: int


def compute_stats(
    frequencies: list[int],
    values: list[float],
    unit: str,
    start_hz: int,
    stop_hz: int,
) -> StatsResult:
    """Compute statistics over the frequency range ``[start_hz, stop_hz]``.

    *unit* determines the averaging method (brief 6.4):

    - ``dBm`` (power-ratio dB, factor 10): linear-mW average.
    - ``dBmV``, ``dBuV`` (voltage-ratio dB, factor 20): RMS-style average.
    - ``V``, ``Vpp`` (linear voltage): RMS across frequency bins.
    - ``W`` (linear power): plain arithmetic mean.
    - ``RAW``: plain arithmetic mean (no physical meaning claimed).
    """
    if not frequencies or len(frequencies) != len(values):
        raise ValueError("frequencies and values must be non-empty and equal length")

    subset = _filter(frequencies, values, start_hz, stop_hz)
    if not subset[0]:
        raise ValueError(f"no data points in range {start_hz}-{stop_hz} Hz")

    freqs, vals = subset
    avg = _average(vals, unit)
    med = _median(vals)
    vmin, fmin = vals[0], freqs[0]
    vmax, fmax = vals[0], freqs[0]
    for f, v in zip(freqs, vals):
        if v < vmin:
            vmin, fmin = v, f
        if v > vmax:
            vmax, fmax = v, f

    return StatsResult(
        average=avg,
        median=med,
        minimum=vmin,
        min_freq=fmin,
        maximum=vmax,
        max_freq=fmax,
    )


# -- internal --------------------------------------------------------------


def _filter(freqs, vals, start, stop):
    out_f: list[int] = []
    out_v: list[float] = []
    for f, v in zip(freqs, vals):
        if start <= f <= stop:
            out_f.append(f)
            out_v.append(v)
    return out_f, out_v


def _average(values: list[float], unit: str) -> float:
    if unit == "dBm":
        lin = [10 ** (v / 10) for v in values]
        return 10 * math.log10(sum(lin) / len(lin))
    if unit in ("dBmV", "dBuV"):
        sq = [(10 ** (v / 20)) ** 2 for v in values]
        rms = math.sqrt(sum(sq) / len(sq))
        return 20 * math.log10(rms)
    if unit in ("V", "Vpp"):
        sq = [v**2 for v in values]
        return math.sqrt(sum(sq) / len(sq))
    # W, RAW, or unknown: plain arithmetic mean.
    return sum(values) / len(values)


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2
