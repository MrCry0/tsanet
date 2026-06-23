"""Discover tinySA devices on serial ports (brief 2.4).

Port enumeration and port opening are injected so discovery is testable
without hardware. The hub wires in the real pyserial-backed adapters at the
bottom of this module.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from tsanet.common.errors import DeviceError
from tsanet.device.commands import device as device_commands
from tsanet.device.model import DeviceInfo, parse_version
from tsanet.device.transport import SerialPort, TinySA

#: Returns the names of candidate serial ports.
PortLister = Callable[[], Iterable[str]]

#: Opens a named serial port, returning something the transport can drive.
PortOpener = Callable[[str], SerialPort]


@dataclass(frozen=True)
class DiscoveredDevice:
    """A tinySA found on a serial port."""

    port: str
    info: DeviceInfo


def probe(port: SerialPort, *, attempts: int = 3) -> DeviceInfo | None:
    """Identify a tinySA on an open port, or return ``None`` if it is not one.

    Sends ``version`` and parses the reply, retrying up to ``attempts`` times.
    The device sometimes emits malformed output right after boot, so a failed
    parse is retried rather than treated as final (brief 2.4).
    """
    tx = TinySA(port)
    for _ in range(attempts):
        try:
            return parse_version(device_commands.get_version(tx))
        except DeviceError:
            continue
    return None


def discover(
    list_ports: PortLister,
    open_port: PortOpener,
    *,
    attempts: int = 3,
) -> list[DiscoveredDevice]:
    """Scan every listed port and return the tinySA devices found.

    Ports that cannot be opened, or do not answer as a tinySA, are skipped.
    Each port is closed again after probing if it exposes a ``close`` method.
    """
    found: list[DiscoveredDevice] = []
    for name in list_ports():
        try:
            port = open_port(name)
        except (OSError, DeviceError):
            continue
        try:
            info = probe(port, attempts=attempts)
        finally:
            _close(port)
        if info is not None:
            found.append(DiscoveredDevice(port=name, info=info))
    return found


def _close(port: SerialPort) -> None:
    close = getattr(port, "close", None)
    if callable(close):
        close()


def list_serial_ports() -> list[str]:
    """List candidate serial port device names using pyserial.

    Requires the ``hub`` extra (pyserial).
    """
    from serial.tools import list_ports

    return [port.device for port in list_ports.comports()]


def open_serial_port(name: str, *, baudrate: int = 115200, timeout: float = 1.0) -> SerialPort:
    """Open a serial port using pyserial.

    The tinySA is a USB CDC device, so the baud rate is nominal; ``timeout``
    bounds each read so an unresponsive port surfaces as a device timeout
    rather than hanging. Requires the ``hub`` extra (pyserial).
    """
    import serial

    return serial.Serial(name, baudrate=baudrate, timeout=timeout)
