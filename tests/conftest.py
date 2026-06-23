"""Shared test fixtures."""

from __future__ import annotations

import pytest

from fakeserial import FakeSerial


@pytest.fixture
def fake_serial():
    return FakeSerial
