"""Low-level tinySA serial transport.

Ported from ``go-tinysa/protocol.go``. The device echoes every command back,
then emits the response, then a ``ch> `` prompt. String responses end with
``\\r\\nch> ``; binary responses (``capture``) end with just ``ch> `` and no
preceding newline. The device occasionally emits malformed output right after
boot, so reads that do not reach the prompt are retried (brief 4).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from tsanet.common.errors import DeviceTimeout, ProtocolError

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


class TinySA:
    """Send commands to a tinySA over a serial port and read framed responses."""

    def __init__(self, port: SerialPort, *, attempts: int = 3) -> None:
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        self._port = port
        self._attempts = attempts

    def send(self, command: str) -> str:
        """Send a command and return its text response, framing stripped."""
        raw = self._exchange(command, self._read_text_response)
        return self._strip(command, raw)

    def send_binary(self, command: str, expected_len: int) -> bytes:
        """Send a command and return ``expected_len`` bytes of binary payload.

        Used for ``capture``, whose payload may contain bytes that look like
        the prompt, so the length is known up front rather than scanned for.
        """

        def read_binary() -> bytes:
            self._port.read_until(b"\n")  # consume the echoed command line
            payload = self._read_exact(expected_len)
            prompt = self._read_exact(len(PROMPT))
            if prompt != PROMPT:
                raise ProtocolError(f"expected prompt after binary payload, got {prompt!r}")
            return payload

        return self._exchange(command, read_binary)

    def write_only(self, command: str) -> None:
        """Send a command without waiting for a prompt (e.g. ``reset``)."""
        self._port.reset_input_buffer()
        self._port.write(command.encode("ascii") + LINE_TERMINATOR)

    def _exchange(self, command: str, reader):
        last_error: DeviceTimeout | None = None
        for _ in range(self._attempts):
            self._port.reset_input_buffer()
            self._port.write(command.encode("ascii") + LINE_TERMINATOR)
            try:
                return reader()
            except DeviceTimeout as error:
                last_error = error
        assert last_error is not None
        raise last_error

    def _read_text_response(self) -> bytes:
        data = self._port.read_until(PROMPT)
        if not data.endswith(PROMPT):
            raise DeviceTimeout(f"no prompt in response: {data!r}")
        return data

    def _read_exact(self, count: int) -> bytes:
        chunks: list[bytes] = []
        remaining = count
        while remaining > 0:
            chunk = self._port.read(remaining)
            if not chunk:
                raise DeviceTimeout(f"expected {count} bytes, got {count - remaining}")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    @staticmethod
    def _strip(command: str, raw: bytes) -> str:
        body = raw[: -len(PROMPT)]
        echo = command.encode("ascii")
        if body.startswith(echo):
            body = body[len(echo) :]
        return body.strip(b"\r\n").decode("ascii", errors="replace")
