"""Shared logging configuration for tsanet."""

from __future__ import annotations

import logging
import sys


# Standard tsanet logger names used throughout the codebase.
# Import these and use ``logging.getLogger(name)`` in each module.
HUB = "tsanet.hub"
CONTROLLER = "tsanet.ctl"
RPC = "tsanet.rpc"
DEVICE = "tsanet.device"
GUI = "tsanet.gui"


def configure(level: int, *, stream=sys.stderr) -> None:
    """Set up logging for the entire tsanet package."""

    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger("tsanet")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
