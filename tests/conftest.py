"""Shared test fixtures."""

from __future__ import annotations

import pytest

from fakeserial import FakeSerial


@pytest.fixture
def fake_serial():
    return FakeSerial


def pytest_addoption(parser):
    parser.addoption(
        "--run-hardware", action="store_true", default=False,
        help="run tests that need a real tinySA device",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "hardware: requires a real tinySA device")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-hardware"):
        return
    skip = pytest.mark.skip(reason="pass --run-hardware to enable")
    for item in items:
        if item.get_closest_marker("hardware"):
            item.add_marker(skip)
