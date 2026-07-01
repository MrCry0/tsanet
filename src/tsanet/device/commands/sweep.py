"""Sweep commands (brief 4: Sweep)."""

from __future__ import annotations

from tsanet.device.transport import TinySA


def get(tx: TinySA) -> str:
    return tx.send("sweep")


def get_status(tx: TinySA) -> str:
    return tx.send("status")


def set_mode(tx: TinySA, mode: str) -> str:
    return tx.send(f"sweep {mode}")


def set_start(tx: TinySA, hz: int) -> str:
    return tx.send(f"sweep start {hz}")


def set_stop(tx: TinySA, hz: int) -> str:
    return tx.send(f"sweep stop {hz}")


def set_center(tx: TinySA, hz: int) -> str:
    return tx.send(f"sweep center {hz}")


def set_span(tx: TinySA, hz: int) -> str:
    return tx.send(f"sweep span {hz}")


def set_cw(tx: TinySA, hz: int) -> str:
    return tx.send(f"sweep cw {hz}")


def set_start_stop(tx: TinySA, start: int, stop: int, points: int | None = None) -> str:
    if points is None:
        return tx.send(f"sweep {start} {stop}")
    return tx.send(f"sweep {start} {stop} {points}")


def set_time(tx: TinySA, microseconds: int) -> str:
    return tx.send(f"sweeptime {microseconds}u")


def set_rbw(tx: TinySA, value: int | str) -> str:
    """Set resolution bandwidth to ``value`` kHz (3-600), or ``"auto"``."""
    return tx.send(f"rbw {value}")


def set_trigger(tx: TinySA, mode: str) -> str:
    """Set the sweep trigger mode: ``"auto"``, ``"normal"``, or ``"single"``."""
    return tx.send(f"trigger {mode}")


def pause(tx: TinySA) -> str:
    return tx.send("pause")


def resume(tx: TinySA) -> str:
    return tx.send("resume")
