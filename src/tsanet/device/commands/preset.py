"""Preset commands (brief 4: Preset).

``save <id>`` writes a device preset slot. This is distinct from saving a file
on the controller, which is not a wire command at all (brief 5).
"""

from __future__ import annotations

from tsanet.device.transport import TinySA


def load(tx: TinySA, preset_id: int) -> str:
    return tx.send(f"load {preset_id}")


def save(tx: TinySA, preset_id: int) -> str:
    return tx.send(f"save {preset_id}")
