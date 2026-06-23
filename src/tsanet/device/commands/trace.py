"""Trace commands (brief 4: Trace and Level).

The Level area from tsactl is not a real device subsystem; its commands send
``trace ...`` on the wire and live here (brief 5).
"""

from __future__ import annotations

from tsanet.device.model import VALID_CALC, VALID_UNITS
from tsanet.device.transport import TinySA


def get(tx: TinySA, trace_id: int) -> str:
    return tx.send(f"trace {trace_id}")


def get_all(tx: TinySA) -> str:
    return tx.send("trace")


def get_frequencies(tx: TinySA) -> str:
    return tx.send("frequencies")


def fetch_value(tx: TinySA, trace_id: int) -> str:
    return tx.send(f"trace {trace_id} value")


def enable(tx: TinySA, trace_id: int) -> str:
    return tx.send(f"trace {trace_id} view on")


def disable(tx: TinySA, trace_id: int) -> str:
    return tx.send(f"trace {trace_id} view off")


def enable_calc(tx: TinySA, trace_id: int, calc: str) -> str:
    if calc not in VALID_CALC:
        raise ValueError(f"invalid calc type: {calc!r}")
    return tx.send(f"calc {trace_id} {calc}")


def disable_calc(tx: TinySA, trace_id: int) -> str:
    return tx.send(f"calc {trace_id} off")


def set_unit(tx: TinySA, unit: str) -> str:
    if unit not in VALID_UNITS:
        raise ValueError(f"invalid unit: {unit!r}")
    return tx.send(f"trace {unit}")


def set_ref_level(tx: TinySA, dbm: float) -> str:
    return tx.send(f"trace reflevel {dbm}")


def set_ref_level_auto(tx: TinySA) -> str:
    return tx.send("trace reflevel auto")


def set_scale(tx: TinySA, level: float) -> str:
    return tx.send(f"trace scale {level}")
