"""Low-level tinySA serial transport.

The ``TinySA`` class is now backed by the tsapython library via
``tsanet.device.adapter``.  The ``SerialPort`` protocol remains here
for type-checking and test usage.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from tsanet.device.adapter import TinySA  # noqa: F401 — re-export

#: Shell prompt that terminates every device response.
PROMPT = b"ch> "

#: Line terminator sent after each command.
LINE_TERMINATOR = b"\r"


@runtime_checkable
class SerialPort(Protocol):
    """Minimal serial interface, satisfied by ``serial.Serial`` and test fakes."""

    def write(self, data: bytes) -> int | None: ...

    def read(self, size: int = 1) -> bytes: ...

    def read_until(self, expected: bytes = b"\n", size: int | None = None) -> bytes: ...

    def reset_input_buffer(self) -> None: ...
