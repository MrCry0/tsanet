"""thinSA adapter over the tsapython library."""

from __future__ import annotations

import logging

from tsapython import tinySA as _tsapython

logger = logging.getLogger("tsanet.device")


class TinySA:
    """thinSA device handle backed by tsapython.

    Maintains the same ``send()`` / ``send_binary()`` / ``write_only()``
    contract as the original transport layer so the hub command modules
    work unchanged.

    When constructed with a port name (*str*), opens a connection through
    tsapython.  When constructed with a :class:`~tsanet.device.transport.SerialPort`
    (e.g. for tests), delegates to the legacy transport via ``_legacy``.
    """

    def __init__(
        self,
        port: str | object,
        *,
        baudrate: int = 115200,
        timeout: float = 1.0,
        attempts: int = 3,
    ) -> None:
        if isinstance(port, str):
            self._tsa = _tsapython()
            ok = self._tsa.connect(port, timeout=timeout)
            if not ok:
                raise ConnectionError(f"failed to connect to {port}")
            self._tsa.set_error_byte_return(False)
            self.port = port
            self._legacy = None
        else:
            # SerialPort-compatible object — use legacy transport (test path)
            from tsanet.device._legacy import TinySA as LegacyTinySA

            self._legacy = LegacyTinySA(port, attempts=attempts)
            self.port = getattr(port, "port", getattr(port, "name", str(port)))
            self._tsa = None

    def send(self, command: str) -> str:
        """Send a text command and return the cleaned response as a string."""
        if self._legacy is not None:
            return self._legacy.send(command)
        logger.debug("TX: %r", command)
        raw = self._tsa.command(command)
        result = raw.decode("ascii", errors="replace").strip()
        logger.debug("RX: %r -> %r", command, result)
        return result

    def send_binary(self, command: str, expected_len: int) -> bytes:
        """Send a command and return binary payload of *expected_len* bytes."""
        if self._legacy is not None:
            return self._legacy.send_binary(command, expected_len)
        logger.debug("TX binary: %r (expect %d bytes)", command, expected_len)
        if command.startswith("capture"):
            raw = self._tsa.capture()
            result = bytes(raw)
            if len(result) != expected_len:
                logger.warning(
                    "capture size mismatch: expected %d, got %d",
                    expected_len,
                    len(result),
                )
                if len(result) < expected_len:
                    result += b"\x00" * (expected_len - len(result))
                else:
                    result = result[:expected_len]
            logger.debug("RX binary: %r -> %d bytes", command, len(result))
            return result
        raw = self._tsa.command(command)
        result = bytes(raw)
        logger.debug("RX binary: %r -> %d bytes", command, len(result))
        return result

    def write_only(self, command: str) -> None:
        """Send a command without waiting for a response."""
        if self._legacy is not None:
            return self._legacy.write_only(command)
        logger.debug("TX write-only: %r", command)
        self._tsa.command(command)

    def close(self) -> None:
        """Release the underlying serial connection."""
        if self._legacy is not None:
            close_fn = getattr(self._legacy._port, "close", None)
            if callable(close_fn):
                close_fn()
            return
        self._tsa.disconnect()
