"""Tests for the hub device registry and hotplug poller."""

from __future__ import annotations

import pytest
from fakeserial import FakeDevicePort

from tsanet.device.model import Model
from tsanet.hub.registry import DeviceRegistry, RegistryPoller


class RecordingOpener:
    """Opens fake ports, remembering each handle and which ports fail."""

    def __init__(self, devices: dict[str, bytes | None], failing: set[str] | None = None):
        self._devices = devices
        self._failing = failing or set()
        self.opened: dict[str, FakeDevicePort] = {}

    def __call__(self, name: str) -> FakeDevicePort:
        if name in self._failing:
            raise OSError("port busy")
        port = FakeDevicePort(body=self._devices[name])
        self.opened[name] = port
        return port


def test_scan_indexes_tinysa_devices():
    opener = RecordingOpener(
        {"/dev/ttyACM0": b"tinySA4_v1.4 HW Version:V0.4.5.1", "/dev/ttyUSB9": None}
    )
    ports = ["/dev/ttyACM0", "/dev/ttyUSB9"]
    registry = DeviceRegistry(lambda: ports, opener)

    registry.scan()
    devices = registry.list()

    assert [d.device_id for d in devices] == ["/dev/ttyACM0"]
    assert devices[0].info.model is Model.ULTRA
    assert devices[0].busy is False
    # A non-tinySA port is opened, found wanting, and closed.
    assert opener.opened["/dev/ttyUSB9"].closed is True


def test_scan_is_idempotent():
    opener = RecordingOpener({"/dev/ttyACM0": b"tinySA4_v1.4 HW Version:V0.4.5.1"})
    registry = DeviceRegistry(lambda: ["/dev/ttyACM0"], opener)

    registry.scan()
    registry.scan()

    assert len(registry.list()) == 1
    assert len(opener.opened) == 1  # not reopened on the second scan


def test_scan_drops_and_closes_removed_devices():
    opener = RecordingOpener(
        {
            "/dev/ttyACM0": b"tinySA4_v1.4 HW Version:V0.4.5.1",
            "/dev/ttyACM1": b"tinySA4_v1.4 HW Version:V0.4.5.1",
        }
    )
    ports = ["/dev/ttyACM0"]
    registry = DeviceRegistry(lambda: ports, opener)

    registry.scan()
    assert [d.port for d in registry.list()] == ["/dev/ttyACM0"]

    ports[:] = ["/dev/ttyACM1"]  # ACM0 unplugged, ACM1 plugged in
    registry.scan()

    assert [d.port for d in registry.list()] == ["/dev/ttyACM1"]
    assert opener.opened["/dev/ttyACM0"].closed is True


def test_get_and_set_busy():
    opener = RecordingOpener({"/dev/ttyACM0": b"tinySA4_v1.4 HW Version:V0.4.5.1"})
    registry = DeviceRegistry(lambda: ["/dev/ttyACM0"], opener)
    registry.scan()

    registry.set_busy("/dev/ttyACM0", True)
    assert registry.get("/dev/ttyACM0").busy is True

    with pytest.raises(KeyError):
        registry.get("/dev/nonexistent")


def test_close_closes_all_connections():
    opener = RecordingOpener({"/dev/ttyACM0": b"tinySA4_v1.4 HW Version:V0.4.5.1"})
    registry = DeviceRegistry(lambda: ["/dev/ttyACM0"], opener)
    registry.scan()

    registry.close()

    assert registry.list() == []
    assert opener.opened["/dev/ttyACM0"].closed is True


def test_poller_scans_immediately_and_stops_cleanly():
    opener = RecordingOpener({"/dev/ttyACM0": b"tinySA4_v1.4 HW Version:V0.4.5.1"})
    registry = DeviceRegistry(lambda: ["/dev/ttyACM0"], opener)
    poller = RegistryPoller(registry, interval=0.01)

    poller.start()
    try:
        assert len(registry.list()) == 1  # first scan ran synchronously in start()
    finally:
        poller.stop()


def test_poller_rejects_nonpositive_interval():
    opener = RecordingOpener({})
    registry = DeviceRegistry(lambda: [], opener)
    with pytest.raises(ValueError):
        RegistryPoller(registry, interval=0)
