"""Trace stats dialog (brief 6.4, 10)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from tsanet.controller.rpc_client import RpcClient
from tsanet.controller.stats import compute_stats
from tsanet.device.model import VALID_UNITS


class StatsDialog(QDialog):
    def __init__(self, rpc: RpcClient, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trace Statistics")
        self.setMinimumWidth(420)
        self._rpc = rpc

        self._trace_id = QLineEdit("1")
        self._start = QLineEdit("410.5mhz")
        self._stop = QLineEdit("600mhz")
        self._unit = QComboBox()
        self._unit.addItems(sorted(VALID_UNITS))
        self._unit.setCurrentText("dBm")

        form = QFormLayout()
        form.addRow("Trace ID:", self._trace_id)
        form.addRow("Start:", self._start)
        form.addRow("Stop:", self._stop)
        form.addRow("Unit:", self._unit)

        calc_btn = QPushButton("Calculate")
        calc_btn.clicked.connect(self._calculate)

        self._result = QTextEdit()
        self._result.setReadOnly(True)
        self._result.setMinimumHeight(120)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(calc_btn)
        layout.addWidget(self._result)

    def _calculate(self):
        from tsanet.controller.parse import parse_frequency

        try:
            tid = int(self._trace_id.text())
            start_hz = parse_frequency(self._start.text())
            stop_hz = parse_frequency(self._stop.text())
        except ValueError as exc:
            self._result.setText(f"Parse error: {exc}")
            return

        try:
            data = self._rpc.call("trace", "fetch_data", ids=[tid])
        except Exception as exc:
            self._result.setText(f"RPC error: {exc}")
            return

        unit = self._unit.currentText()
        result = compute_stats(
            data["frequencies"], data["traces"][tid], unit, start_hz, stop_hz,
        )

        n = sum(1 for f in data["frequencies"] if start_hz <= f <= stop_hz)
        self._result.setText(
            f"Trace {tid} stats  ({n} points), unit: {unit}\n\n"
            f"  Average power : {result.average:.1f} {unit}\n"
            f"  Median        : {result.median:.1f} {unit}\n"
            f"  Min           : {result.minimum:.1f} {unit}  @ {_fmt(result.min_freq)}\n"
            f"  Max           : {result.maximum:.1f} {unit}  @ {_fmt(result.max_freq)}\n"
        )


def _fmt(hz: int) -> str:
    if hz >= 1_000_000_000:
        return f"{hz / 1e9:.3f} GHz"
    if hz >= 1_000_000:
        return f"{hz / 1e6:.3f} MHz"
    if hz >= 1_000:
        return f"{hz / 1e3:.3f} kHz"
    return f"{hz} Hz"
