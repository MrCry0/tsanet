"""Discover tinySA devices on serial ports (brief 2.4).

Port enumeration is injected so discovery is testable without hardware.
Device probing now uses the tsapython-backed adapter.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from tsanet.common.errors import DeviceError
from tsanet.device.commands import device as device_commands
from tsanet.device.model import DeviceInfo, parse_version
from tsanet.device.transport import TinySA

#: Returns the names of candidate serial ports.
PortLister = Callable[[], Iterable[str]]

#: Opens a named serial port, returning something the transport can drive.
PortOpener = Callable[[str], object]


@dataclass(frozen=True)
class DiscoveredDevice:
    """A tinySA found on a serial port."""

    port: str
    info: DeviceInfo


def probe(port: str | object, *, attempts: int = 3) -> DeviceInfo | None:
    """Identify a tinySA on *port*, or return ``None`` if it is not one.

    *port* can be a device path string (production path through tsapython)
    or a ``SerialPort``-compatible object (test path through legacy
    transport).
    """
    # Detect test fakes that implement the SerialPort protocol but aren't
    # real PySerial or strings.
    if not isinstance(port, str) and not hasattr(port, "baudrate"):
        # SerialPort-compatible object (e.g. FakeDevicePort) — legacy path
        from tsanet.device._legacy import TinySA as LegacyTinySA

        tx = LegacyTinySA(port)
        for _ in range(attempts):
            try:
                return parse_version(device_commands.get_version(tx))
            except DeviceError:
                continue
        return None

    # Production path: port name string
    for _ in range(attempts):
        try:
            tx = TinySA(port)
        except (OSError, DeviceError, ConnectionError):
            return None
        try:
            return parse_version(device_commands.get_version(tx))
        except DeviceError:
            continue
        finally:
            tx.close()
    return None


def discover(
    list_ports: PortLister,
    open_port: PortOpener | None = None,
    *,
    attempts: int = 3,
) -> list[DiscoveredDevice]:
    """Scan every listed port and return the tinySA devices found.

    If *open_port* is provided, it is used to open each port (test path
    through legacy transport). Otherwise, ``probe()`` opens connections
    directly through tsapython.
    """
    found: list[DiscoveredDevice] = []
    for name in list_ports():
        if open_port is not None:
            try:
                port = open_port(name)
            except (OSError, DeviceError):
                continue
            info = probe(port, attempts=attempts)
            close_fn = getattr(port, "close", None)
            if callable(close_fn):
                close_fn()
        else:
            info = probe(name, attempts=attempts)
        if info is not None:
            found.append(DiscoveredDevice(port=name, info=info))
    return found


def list_serial_ports() -> list[str]:
    """List candidate serial port device names using pyserial.

    Only ports matching ``/dev/ttyACM*`` are returned — those are the
    USB CDC ACM devices that the tinySA presents as.

    Requires the ``hub`` extra (pyserial).
    """
    from serial.tools import list_ports

    return [port.device for port in list_ports.comports() if "/dev/ttyACM" in port.device]
