"""Trace stats dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
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
        self.setMinimumWidth(480)
        self._rpc = rpc

        self._trace_id = QLineEdit("1")
        self._trace_id.setToolTip("Trace channel number (1-4 on tinySA Ultra)")
        self._start = QLineEdit("410.5mhz")
        self._start.setToolTip("Start of the frequency sub-range to analyze")
        self._stop = QLineEdit("600mhz")
        self._stop.setToolTip("End of the frequency sub-range to analyze")
        self._unit = QComboBox()
        self._unit.addItems(sorted(VALID_UNITS))
        self._unit.setCurrentText("dBm")
        self._unit.setToolTip(
            "Display unit: dBm (power dB), dBmV/dBuV (voltage dB), "
            "V, Vpp, W, or RAW (no physical meaning)"
        )
        self._antenna = QLineEdit()
        self._antenna.setToolTip(
            "Antenna factor in dB/m (optional, enables field strength in dBuV/m)"
        )
        self._antenna.setPlaceholderText("e.g. 12.5")

        form = QFormLayout()
        form.addRow("Trace ID:", self._trace_id)
        form.addRow("Start:", self._start)
        form.addRow("Stop:", self._stop)
        form.addRow("Unit:", self._unit)
        form.addRow("Ant. factor (dB/m):", self._antenna)

        calc_btn = QPushButton("Calculate")
        calc_btn.setToolTip("Fetch trace data from the device and compute statistics")
        calc_btn.clicked.connect(self._calculate)

        hint = QLabel(
            "Statistics: average, median, min/max, channel power, "
            "occupied bandwidth (99% OBW), PAPR, flatness, field strength"
        )
        hint.setWordWrap(True)

        self._result = QTextEdit()
        self._result.setReadOnly(True)
        self._result.setMinimumHeight(200)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(calc_btn)
        layout.addWidget(hint)
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

        af_text = self._antenna.text().strip()
        af = float(af_text) if af_text else None
        unit = self._unit.currentText()

        try:
            result = compute_stats(
                data["frequencies"],
                data["traces"][str(tid)],
                unit,
                start_hz,
                stop_hz,
                antenna_factor=af,
            )
        except Exception as exc:
            self._result.setText(f"Compute error: {exc}")
            return

        n = sum(1 for f in data["frequencies"] if start_hz <= f <= stop_hz)
        lines = [
            f"Trace {tid} statistics  ({n} points, unit: {unit})",
            "",
            f"  Average power        : {result.average:.1f} {unit}",
            f"  Median               : {result.median:.1f} {unit}",
            f"  Minimum              : {result.minimum:.1f} {unit}  @ {_fmt(result.min_freq)}",
            f"  Maximum              : {result.maximum:.1f} {unit}  @ {_fmt(result.max_freq)}",
            f"  Channel power        : {result.channel_power:.1f} {unit}",
            f"  Occupied bandwidth   : {_fmt(result.occupied_bandwidth_hz)}  (99% OBW)",
            f"  PAPR (crest factor)  : {result.papr_db:.1f} dB",
            f"  Flatness             : {result.flatness_db:.1f} dB",
        ]
        if result.field_strength_dbuvm is not None:
            lines.append(f"  Field strength       : {result.field_strength_dbuvm:.1f} dBuV/m")
        self._result.setText("\n".join(lines))


def _fmt(hz: int) -> str:
    if hz >= 1_000_000_000:
        return f"{hz / 1e9:.3f} GHz"
    if hz >= 1_000_000:
        return f"{hz / 1e6:.3f} MHz"
    if hz >= 1_000:
        return f"{hz / 1e3:.3f} kHz"
    return f"{hz} Hz"
