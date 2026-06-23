"""Tests for device discovery: probing and port scanning."""

from __future__ import annotations

from fakeserial import FakeDevicePort

from tsanet.device.discovery import discover, probe
from tsanet.device.model import Model


def test_probe_identifies_tinysa():
    info = probe(FakeDevicePort())
    assert info is not None
    assert info.model is Model.ULTRA


def test_probe_returns_none_for_non_tinysa():
    assert probe(FakeDevicePort(body=None), attempts=2) is None


def test_discover_returns_only_responding_ports():
    ports = {
        "/dev/ttyACM0": FakeDevicePort(),
        "/dev/ttyUSB9": FakeDevicePort(body=None),  # not a tinySA
    }

    def open_port(name):
        return ports[name]

    found = discover(lambda: ports.keys(), open_port)

    assert [d.port for d in found] == ["/dev/ttyACM0"]
    assert found[0].info.model is Model.ULTRA


def test_discover_skips_ports_that_fail_to_open():
    def open_port(name):
        raise OSError("port busy")

    found = discover(lambda: ["/dev/ttyACM0"], open_port)

    assert found == []


def test_discover_closes_probed_ports():
    port = FakeDevicePort()
    discover(lambda: ["/dev/ttyACM0"], lambda name: port)

    assert port.closed is True
