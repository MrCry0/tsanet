"""Sweep value mismatch detection shared between CLI and GUI."""

from __future__ import annotations


def sweep_mismatch_warning(requested, s: int, t: int, p: int | None) -> str | None:
    """Describe any requested sweep value the device did not apply as-is.

    The device can silently clamp a request (e.g. a 900-point request
    capped to its 450-point maximum) without returning an error.
    """
    if not requested:
        return None
    actual = {
        "start": s,
        "stop": t,
        "points": p,
        "center": (s + t) // 2,
        "span": t - s,
        "cw": s,
    }
    mismatches = []
    for key, want in requested.items():
        got = actual.get(key)
        if want is None or got is None or want == got:
            continue
        shown = str(want) if key == "points" else _fmt(want)
        shown_got = str(got) if key == "points" else _fmt(got)
        mismatches.append(f"{key} {shown} -> {shown_got}")
    if not mismatches:
        return None
    return "device adjusted: " + ", ".join(mismatches)


def _fmt(hz: int) -> str:
    if hz >= 1_000_000_000:
        return f"{hz / 1e9:.3f} GHz"
    if hz >= 1_000_000:
        return f"{hz / 1e6:.3f} MHz"
    if hz >= 1_000:
        return f"{hz / 1e3:.3f} kHz"
    return f"{hz} Hz"
