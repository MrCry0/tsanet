"""Device commands (brief 4: Device)."""

from __future__ import annotations

from tsanet.device.transport import TinySA


def get_version(tx: TinySA) -> str:
    return tx.send("version")


def get_id(tx: TinySA) -> str:
    return tx.send("deviceid")


def set_id(tx: TinySA, device_id: int) -> str:
    return tx.send(f"deviceid {device_id}")


def get_battery(tx: TinySA) -> str:
    return tx.send("vbat")


def get_battery_offset(tx: TinySA) -> str:
    return tx.send("vbat_offset")


def set_battery_offset(tx: TinySA, millivolts: int) -> str:
    return tx.send(f"vbat_offset {millivolts}")


def reset(tx: TinySA, dfu: bool = False) -> None:
    """Reset the device. The device reboots and sends no prompt back."""
    tx.write_only("reset dfu" if dfu else "reset")
