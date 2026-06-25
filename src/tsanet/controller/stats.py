"""Trace statistics over a frequency sub-range (brief 6.4).

Computes average power, median, min@freq, and max@freq from trace data,
with unit-aware linear averaging.  This is a controller-side computation
on top of ``trace.fetch_data`` — no new Hub RPC is needed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


#: Fraction of total power that must fall inside the occupied bandwidth
#: (the standard ITU-R/FCC "99% occupied bandwidth" convention).
_OBW_FRACTION = 0.99


@dataclass
class StatsResult:
    average: float
    median: float
    minimum: float
    min_freq: int
    maximum: float
    max_freq: int
    occupied_bandwidth_hz: int
    papr_db: float
    flatness_db: float
    field_strength_dbuvm: float | None = None


def compute_stats(
    frequencies: list[int],
    values: list[float],
    unit: str,
    start_hz: int,
    stop_hz: int,
    antenna_factor: float | None = None,
) -> StatsResult:
    """Compute statistics over the frequency range ``[start_hz, stop_hz]``.

    *unit* determines the averaging method (brief 6.4):

    - ``dBm`` (power-ratio dB, factor 10): linear-mW average.
    - ``dBmV``, ``dBuV`` (voltage-ratio dB, factor 20): RMS-style average.
    - ``V``, ``Vpp`` (linear voltage): RMS across frequency bins.
    - ``W`` (linear power): plain arithmetic mean.
    - ``RAW``: plain arithmetic mean (no physical meaning claimed).

    If *antenna_factor* (dB/m) is given, also reports field strength in
    dBuV/m: ``E = V[dBuV] + antenna_factor``, where the average level is
    first converted to dBuV at a 50 ohm reference. Raises :class:`ValueError`
    for ``unit="RAW"``, which has no defined physical conversion.
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

    field_strength = None
    if antenna_factor is not None:
        field_strength = _to_dbuv(avg, unit) + antenna_factor

    return StatsResult(
        average=avg,
        median=med,
        minimum=vmin,
        min_freq=fmin,
        maximum=vmax,
        max_freq=fmax,
        occupied_bandwidth_hz=_occupied_bandwidth(freqs, vals, unit),
        papr_db=_papr_db(vals, unit),
        flatness_db=_flatness_db(vmin, vmax, unit),
        field_strength_dbuvm=field_strength,
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


def _linear_power(values: list[float], unit: str) -> list[float]:
    """Power-proportional linear values, for power-domain math (OBW/PAPR/flatness).

    Both dB-power (factor 10) and dB-voltage (factor 20) units reduce to the
    same ``10**(v/10)`` expression here: squaring a factor-20 linear voltage
    is ``(10**(v/20))**2 == 10**(v/10)``, so it is power-proportional too.
    """
    if unit in ("dBm", "dBmV", "dBuV"):
        return [10 ** (v / 10) for v in values]
    if unit in ("V", "Vpp"):
        return [v * v for v in values]
    # W, RAW: already linear, or no defined power relationship.
    return list(values)


def _occupied_bandwidth(freqs: list[int], values: list[float], unit: str) -> int:
    """Bandwidth containing ``_OBW_FRACTION`` of the total power.

    Standard ITU-R/FCC definition: split the power outside the band evenly
    between the two edges (here 0.5% below and 0.5% above for the 99% case).
    """
    power = _linear_power(values, unit)
    total = sum(power)
    if total <= 0:
        return 0

    edge = (1.0 - _OBW_FRACTION) / 2.0
    lo_target = edge * total
    hi_target = (1.0 - edge) * total

    cumulative = 0.0
    lo_freq = freqs[0]
    hi_freq = freqs[-1]
    lo_found = False
    for f, p in zip(freqs, power):
        cumulative += p
        if not lo_found and cumulative >= lo_target:
            lo_freq = f
            lo_found = True
        if cumulative >= hi_target:
            hi_freq = f
            break
    return hi_freq - lo_freq


def _papr_db(values: list[float], unit: str) -> float:
    """Peak-to-average power ratio (crest factor), in dB."""
    power = _linear_power(values, unit)
    avg = sum(power) / len(power)
    if avg <= 0:
        raise ValueError("cannot compute PAPR: average power is non-positive")
    return 10 * math.log10(max(power) / avg)


def _flatness_db(vmin: float, vmax: float, unit: str) -> float:
    """Peak-to-trough variation across the range, in dB."""
    lo, hi = _linear_power([vmin, vmax], unit)
    if lo <= 0:
        raise ValueError("cannot compute flatness: minimum value is non-positive")
    return 10 * math.log10(hi / lo)


def _to_dbuv(level: float, unit: str) -> float:
    """Convert a single level to dBuV, assuming a 50 ohm reference for power units."""
    if unit == "dBm":
        return level + 107.0
    if unit == "dBmV":
        return level + 60.0
    if unit == "dBuV":
        return level
    if unit in ("V", "Vpp"):
        if level <= 0:
            raise ValueError("cannot convert a non-positive voltage to dBuV")
        return 20 * math.log10(level) + 120.0
    if unit == "W":
        if level <= 0:
            raise ValueError("cannot convert a non-positive power to dBuV")
        return 10 * math.log10(level * 1000) + 107.0
    raise ValueError(f"field strength is not defined for unit {unit!r}")
