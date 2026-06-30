"""Hub-side registry of connected tinySA devices (brief 2.4, 11.3).

The registry owns the open device connections. ``scan`` reconciles the set of
registered devices with the ports currently present: new tinySA devices are
opened and indexed, and devices whose ports have disappeared are dropped and
closed. A :class:`RegistryPoller` re-runs ``scan`` periodically to pick up
hotplug events.

``device_id`` is currently the serial port path. It is a separate field from
``port`` so the identifier scheme can change later without touching the RPC
surface.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from tsanet.common.errors import DeviceError
from tsanet.device.discovery import PortLister
from tsanet.device.model import DeviceInfo
from tsanet.device.transport import TinySA

logger = logging.getLogger("tsanet.hub.registry")


@dataclass
class RegisteredDevice:
    """A tinySA the hub has indexed and holds an open connection to."""

    device_id: str
    port: str
    info: DeviceInfo
    transport: TinySA
    busy: bool = False


class DeviceRegistry:
    """Tracks connected tinySA devices and their open device connections."""

    def __init__(
        self,
        list_ports: PortLister,
        open_port: object = None,
        *,
        probe_attempts: int = 3,
    ) -> None:
        self._list_ports = list_ports
        self._open_port = open_port
        self._probe_attempts = probe_attempts
        self._devices: dict[str, RegisteredDevice] = {}
        self._lock = threading.Lock()

    def scan(self) -> None:
        """Reconcile indexed devices with the ports currently present."""
        present = set(self._list_ports())
        with self._lock:
            known = set(self._devices)

        for port in sorted(present - known):
            device = self._probe_port(port)
            if device is not None:
                with self._lock:
                    if port not in self._devices:
                        self._devices[port] = device
                        logger.info("device added: %s", port)

        with self._lock:
            for port in sorted(known - present):
                self._drop(port)
                logger.info("device removed: %s", port)

    def list(self) -> list[RegisteredDevice]:
        """Return the indexed devices, ordered by port."""
        with self._lock:
            return [self._devices[port] for port in sorted(self._devices)]

    def get(self, device_id: str) -> RegisteredDevice:
        """Return a device by id, or raise :class:`KeyError` if unknown."""
        with self._lock:
            for device in self._devices.values():
                if device.device_id == device_id:
                    return device
        raise KeyError(device_id)

    def set_busy(self, device_id: str, busy: bool) -> None:
        """Mark a device busy or free."""
        self.get(device_id).busy = busy

    def close(self) -> None:
        """Close every open connection and clear the registry."""
        with self._lock:
            for port in list(self._devices):
                self._drop(port)

    def _probe_port(self, port: str) -> RegisteredDevice | None:
        if self._open_port is not None:
            # Test path: uses caller-provided open_port callback
            try:
                handle = self._open_port(port)
            except (OSError, DeviceError):
                return None
            from tsanet.device import discovery as _discovery

            info = _discovery.probe(handle, attempts=self._probe_attempts)
            if info is None:
                close_fn = getattr(handle, "close", None)
                if callable(close_fn):
                    close_fn()
                return None
            return RegisteredDevice(
                device_id=port,
                port=port,
                info=info,
                transport=TinySA(handle),
            )

        # Production path: probe and connect through tsapython adapter
        from tsanet.device import discovery as _discovery

        info = _discovery.probe(port, attempts=self._probe_attempts)
        if info is None:
            return None
        try:
            transport = TinySA(port)
        except (OSError, DeviceError, ConnectionError):
            return None
        return RegisteredDevice(
            device_id=port,
            port=port,
            info=info,
            transport=transport,
        )

    def _drop(self, port: str) -> None:
        device = self._devices.pop(port, None)
        if device is not None:
            device.transport.close()


class RegistryPoller:
    """Runs :meth:`DeviceRegistry.scan` in a background thread.

    The first scan happens immediately when the thread starts; subsequent
    scans run every ``interval`` seconds.
    """

    def __init__(self, registry: DeviceRegistry, interval: float) -> None:
        if interval <= 0:
            raise ValueError("interval must be positive")
        self._registry = registry
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._registry.scan()
            self._stop.wait(self._interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
