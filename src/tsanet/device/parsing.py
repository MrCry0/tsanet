"""Parse numeric output of the ``frequencies`` and ``trace value`` commands.

These feed the structured result of ``trace.fetch_data`` (brief 6.2), which
the live graph and stats features consume.

NOTE: the exact column layout of these device responses was not captured in
the protocol reference, so the parsers here are deliberately tolerant: a
frequency line yields its first integer token and a trace-value line yields
its last float token (which holds whether the device prints values alone or
as "<frequency> <value>" pairs). Verify and tighten against real hardware
output.
"""

from __future__ import annotations


def parse_frequencies(text: str) -> list[int]:
    """Parse a ``frequencies`` response into a list of integer hertz values."""
    frequencies: list[int] = []
    for line in text.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        try:
            frequencies.append(int(float(tokens[0])))
        except ValueError:
            continue
    return frequencies


def parse_trace_values(text: str) -> list[float]:
    """Parse a ``trace <id> value`` response into a list of float values."""
    values: list[float] = []
    for line in text.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        try:
            values.append(float(tokens[-1]))
        except ValueError:
            continue
    return values
