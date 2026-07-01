"""Signal commands (brief 4: Signal)."""

from __future__ import annotations

from tsanet.device.transport import TinySA


def enable_spur(tx: TinySA) -> str:
    return tx.send("spur on")


def disable_spur(tx: TinySA) -> str:
    return tx.send("spur off")


def enable_auto_spur(tx: TinySA) -> str:
    return tx.send("spur auto")


def enable_lna(tx: TinySA) -> str:
    return tx.send("lna on")


def disable_lna(tx: TinySA) -> str:
    return tx.send("lna off")


def set_attenuation(tx: TinySA, value: int | str) -> str:
    """Set input attenuation to ``value`` dB (0-30), or ``"auto"``."""
    return tx.send(f"attenuate {value}")
