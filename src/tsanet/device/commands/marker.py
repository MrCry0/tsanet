"""Marker commands (brief 4: Marker)."""

from __future__ import annotations

from tsanet.device.transport import TinySA


def get(tx: TinySA, marker_id: int) -> str:
    return tx.send(f"marker {marker_id}")


def get_all(tx: TinySA) -> str:
    return tx.send("marker")


def enable(tx: TinySA, marker_id: int) -> str:
    return tx.send(f"marker {marker_id} on")


def disable(tx: TinySA, marker_id: int) -> str:
    return tx.send(f"marker {marker_id} off")


def set_freq(tx: TinySA, marker_id: int, hz: int) -> str:
    return tx.send(f"marker {marker_id} {hz}")


def set_trace(tx: TinySA, marker_id: int, trace_id: int) -> str:
    return tx.send(f"marker {marker_id} trace {trace_id}")


def move_to_peak(tx: TinySA, marker_id: int) -> str:
    return tx.send(f"marker {marker_id} peak")


def enable_delta(tx: TinySA, marker_id: int, ref_id: int) -> str:
    return tx.send(f"marker {marker_id} delta {ref_id}")


def disable_delta(tx: TinySA, marker_id: int) -> str:
    return tx.send(f"marker {marker_id} delta off")


def enable_tracking(tx: TinySA, marker_id: int) -> str:
    return tx.send(f"marker {marker_id} tracking on")


def disable_tracking(tx: TinySA, marker_id: int) -> str:
    return tx.send(f"marker {marker_id} tracking off")
