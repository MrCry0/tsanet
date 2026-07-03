"""Tests for the Spectrum tab's Signal group controls.

Requires PySide6 (the "gui" extra); skips cleanly otherwise.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tsanet.controller.gui.spectrum_panel import SpectrumPanel  # noqa: E402


class _FakeRpc:
    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    def call(self, domain, op, **kwargs):
        self.calls.append((domain, op, kwargs))
        return None

    def on_event(self, cb):
        pass


@pytest.fixture
def qapp():
    yield QApplication.instance() or QApplication([])


def test_set_sweep_time_sends_sweep_set_time(qapp):
    rpc = _FakeRpc()
    panel = SpectrumPanel(rpc=rpc)
    panel._sweeptime_spin.setValue(2500)

    panel._set_sweep_time()

    assert ("sweep", "set_time", {"us": 2500}) in rpc.calls


def test_set_sweep_time_is_noop_without_rpc(qapp):
    panel = SpectrumPanel(rpc=None)
    panel._sweeptime_spin.setValue(500)

    panel._set_sweep_time()  # must not raise


def test_sweep_time_default_is_zero(qapp):
    panel = SpectrumPanel(rpc=_FakeRpc())
    assert panel._sweeptime_spin.value() == 0
