"""Tests for the single-session manager and force-takeover."""

from __future__ import annotations

import pytest

from tsanet.common.errors import SessionBusy
from tsanet.hub.session import SessionManager


class DummyConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_admit_when_free():
    manager = SessionManager()
    session = manager.admit(DummyConnection(), peer="ctl-1")

    assert manager.current is session
    status = manager.status()
    assert status["active"] is True
    assert status["peer"] == "ctl-1"
    assert status["selected_device"] is None


def test_second_admission_rejected_without_force():
    manager = SessionManager()
    manager.admit(DummyConnection())

    with pytest.raises(SessionBusy):
        manager.admit(DummyConnection())


def test_force_takeover_evicts_incumbent():
    manager = SessionManager()
    first = DummyConnection()
    manager.admit(first)

    second = DummyConnection()
    manager.admit(second, force=True)

    assert first.closed is True
    assert manager.current.connection is second


def test_disconnect_clears_session():
    manager = SessionManager()
    conn = DummyConnection()
    manager.admit(conn)

    manager.disconnect()

    # disconnect clears the session without closing the connection;
    # the caller is responsible for closing.
    assert conn.closed is False
    assert manager.current is None
    assert manager.status() == {"active": False}


def test_select_device_updates_status():
    manager = SessionManager()
    manager.admit(DummyConnection())

    manager.select_device("/dev/ttyACM0")

    assert manager.status()["selected_device"] == "/dev/ttyACM0"


def test_select_device_without_session():
    manager = SessionManager()
    with pytest.raises(SessionBusy):
        manager.select_device("/dev/ttyACM0")
