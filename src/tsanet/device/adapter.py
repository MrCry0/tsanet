"""thinSA adapter over the tsapython library."""

from __future__ import annotations

import logging
import time

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

    def read_scanraw(self, start: int, stop: int, pts: int, timeout: float = 2.0) -> bytes:
        """Fetch one scanraw frame via a tight-poll read, bypassing tsapython.

        tsapython's own ``scan_raw()`` -> ``get_binary_return()`` busy-polls
        with ``time.sleep(0.01)`` whenever the serial buffer is momentarily
        empty -- a real, avoidable latency tax on top of the actual transfer
        time. This reads directly against the underlying pyserial handle
        (``tsapython.tinySA.ser``, a plain public attribute) with
        OS-blocking reads instead, replicating tsapython's own framing
        exactly: the response is ``'{' + 3*pts data bytes + '}'``, and (to
        match ``get_binary_return``'s contract, which callers already
        decode against) this returns ``'{' + data`` with the trailing
        ``'}'`` dropped.

        Reaches around a third-party dependency's internals, so any
        surprise -- a missing ``.ser``, a framing mismatch, a timeout --
        falls back to the normal ``scan_raw()`` call rather than raising.
        The fast path is opt-in (see hub/config.py's ``scanraw_fast_read``)
        and self-healing: never worse than the existing behavior.
        """
        if self._legacy is not None:
            raise NotImplementedError(
                "read_scanraw requires a tsapython-backed connection, not the legacy transport"
            )

        tsa = self._tsa
        ser = getattr(tsa, "ser", None)
        if ser is None:
            logger.debug("read_scanraw: tsapython has no '.ser' attribute; using scan_raw")
            return bytes(tsa.scan_raw(start, stop, pts))

        try:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            ser.write(f"scanraw {start} {stop} {pts} 1\r\n".encode("ascii"))

            frame_len = 1 + 3 * pts + 1  # '{' + 3*pts data bytes + '}'
            buf = bytearray()
            deadline = time.monotonic() + timeout

            # Skip the echoed command line up to the frame's opening '{'.
            while b"{" not in buf:
                chunk = ser.read(1)
                if chunk:
                    buf += chunk
                elif time.monotonic() > deadline:
                    raise TimeoutError("read_scanraw: no frame start '{' before timeout")

            start_idx = buf.index(b"{")
            need = frame_len - (len(buf) - start_idx)
            while need > 0:
                chunk = ser.read(need)
                if chunk:
                    buf += chunk
                    need -= len(chunk)
                elif time.monotonic() > deadline:
                    raise TimeoutError("read_scanraw: short frame before timeout")

            frame = bytes(buf[start_idx : start_idx + frame_len])
            return frame[:-1]  # '{' + data, matching get_binary_return's contract
        except Exception:
            logger.debug("read_scanraw fast path failed; falling back to scan_raw", exc_info=True)
            return bytes(tsa.scan_raw(start, stop, pts))

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
