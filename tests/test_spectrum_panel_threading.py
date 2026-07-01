"""Regression test: SpectrumPanel's single-shot capture must not deadlock.

See test_rpc_client_threading.py for the underlying RpcClient hazard this
guards against (a call() made from inside an event callback can never
return, since the callback runs on the very reader thread that would
deliver the response). This test exercises SpectrumPanel itself, firing a
scanraw event from a real background thread exactly like RpcClient's
reader thread does, and requires PySide6 (the "gui" extra).
"""

from __future__ import annotations

import threading

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tsanet.controller.gui.spectrum_panel import SpectrumPanel  # noqa: E402


class _FakeThreadedRpc:
    """Stands in for RpcClient: records calls, and can fire the registered
    event callback from a real background thread, like the reader loop."""

    def __init__(self, sweep_get_response="100000000 200000000 3"):
        self._cb = None
        self._sweep_get_response = sweep_get_response
        self.calls: list[tuple[str, str, dict]] = []

    def call(self, domain, op, **kwargs):
        self.calls.append((domain, op, kwargs))
        if domain == "sweep" and op == "get":
            return self._sweep_get_response
        return None

    def on_event(self, cb):
        self._cb = cb

    def fire_from_background_thread(self, event) -> threading.Thread:
        t = threading.Thread(target=lambda: self._cb(event), daemon=True)
        t.start()
        return t


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_single_capture_does_not_hang_when_event_fires_on_background_thread(qapp):
    rpc = _FakeThreadedRpc()
    panel = SpectrumPanel(rpc=rpc)
    panel._sw_start.setText("100mhz")
    panel._sw_stop.setText("200mhz")

    panel._single_capture()

    t1 = rpc.fire_from_background_thread({"frequencies": [100, 150, 200]})
    t1.join(timeout=2.0)
    assert not t1.is_alive()

    t2 = rpc.fire_from_background_thread(
        {"frequencies": [100, 150, 200], "level": [-50.0, -40.0, -30.0]}
    )
    t2.join(timeout=2.0)
    assert not t2.is_alive(), "background thread hung -- the deadlock regressed"

    # Pump the Qt event loop so the queued signal is actually delivered.
    QTimer.singleShot(100, qapp.quit)
    qapp.exec()

    assert panel._single_shot is False
    assert panel._subscription_active is False
    assert panel._start_btn.text() == "Start"
    assert panel._status.text() == "Single capture complete"


def test_single_capture_does_not_flip_start_button_to_stop(qapp):
    """The Start button represents continuous streaming; a single capture
    must not visually claim continuous streaming is running."""
    rpc = _FakeThreadedRpc()
    panel = SpectrumPanel(rpc=rpc)
    panel._sw_start.setText("100mhz")
    panel._sw_stop.setText("200mhz")

    panel._single_capture()

    assert panel._start_btn.text() == "Start"
    assert panel._start_btn.isChecked() is False
