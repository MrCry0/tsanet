"""An in-memory fake serial port for driving the TinySA transport in tests."""

from __future__ import annotations


class FakeSerial:
    """A scripted serial port.

    Each ``write`` loads the next canned response into the read buffer, so a
    response of ``b""`` simulates a timeout (no prompt arrives). ``written``
    records the exact bytes sent for wire-format assertions.
    """

    def __init__(self, responses: list[bytes]) -> None:
        self._responses = list(responses)
        self._buffer = b""
        self.written: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.written.append(data)
        self._buffer = self._responses.pop(0) if self._responses else b""
        return len(data)

    def read(self, size: int = 1) -> bytes:
        chunk = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return chunk

    def read_until(self, expected: bytes = b"\n", size: int | None = None) -> bytes:
        index = self._buffer.find(expected)
        if index == -1:
            data, self._buffer = self._buffer, b""
            return data
        end = index + len(expected)
        data, self._buffer = self._buffer[:end], self._buffer[end:]
        return data

    def reset_input_buffer(self) -> None:
        self._buffer = b""


class FakeDevicePort:
    """A serial port that answers every command with a fixed response body.

    Echoes the command, appends ``body`` and a prompt, so it responds
    consistently across repeated probe attempts. ``body=None`` simulates a
    non-tinySA port whose reply never parses as a version.
    """

    def __init__(self, body: bytes | None = b"tinySA4_v1.4 HW Version:V0.4.5.1") -> None:
        self._body = b"garbage" if body is None else body
        self._buffer = b""
        self.closed = False

    def write(self, data: bytes) -> int:
        echo = data.rstrip(b"\r")
        self._buffer = echo + b"\r\n" + self._body + b"\r\nch> "
        return len(data)

    def read(self, size: int = 1) -> bytes:
        chunk = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return chunk

    def read_until(self, expected: bytes = b"\n", size: int | None = None) -> bytes:
        index = self._buffer.find(expected)
        if index == -1:
            data, self._buffer = self._buffer, b""
            return data
        end = index + len(expected)
        data, self._buffer = self._buffer[:end], self._buffer[end:]
        return data

    def reset_input_buffer(self) -> None:
        self._buffer = b""

    def close(self) -> None:
        self.closed = True
