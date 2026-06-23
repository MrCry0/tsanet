"""Menu commands (brief 4: Menu)."""

from __future__ import annotations

from collections.abc import Sequence

from tsanet.device.transport import TinySA


def trigger(tx: TinySA, ids: Sequence[int]) -> str:
    if not ids:
        raise ValueError("menu trigger requires at least one id")
    return tx.send("menu " + " ".join(str(i) for i in ids))
