"""Raw passthrough (brief 4: Raw passthrough).

Sends an arbitrary command verbatim, for commands not modeled above
(e.g. ``scanraw``, ``sd_list``) and forward compatibility.
"""

from __future__ import annotations

from tsanet.device.transport import TinySA


def execute(tx: TinySA, command: str) -> str:
    return tx.send(command)
