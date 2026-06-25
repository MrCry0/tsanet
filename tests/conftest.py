"""Shared test fixtures."""

from __future__ import annotations

import importlib

import pytest

from fakeserial import FakeSerial


@pytest.fixture
def fake_serial():
    return FakeSerial


def pytest_addoption(parser):
    parser.addoption(
        "--run-hardware",
        action="store_true",
        default=False,
        help="run tests that need a real tinySA device (auto-detected by default)",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "hardware: requires a real tinySA device")


def _has_tinysa():
    try:
        importlib.import_module("serial")
    except ImportError:
        return False
    try:
        from serial.tools.list_ports import comports
    except ImportError:
        return False
    try:
        from tsanet.device.discovery import probe as tinysa_probe

        for port_info in comports():
            name = port_info.device
            try:
                import serial

                ser = serial.Serial(name, baudrate=115200, timeout=0.5)
                info = tinysa_probe(ser, attempts=1)
                ser.close()
                if info is not None:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


_HW_CACHED: bool | None = None


def _hardware_available():
    global _HW_CACHED
    if _HW_CACHED is None:
        _HW_CACHED = _has_tinysa()
    return _HW_CACHED


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-hardware"):
        return
    if _hardware_available():
        return
    skip = pytest.mark.skip(reason="no tinySA detected; pass --run-hardware to force")
    for item in items:
        if item.get_closest_marker("hardware"):
            item.add_marker(skip)
