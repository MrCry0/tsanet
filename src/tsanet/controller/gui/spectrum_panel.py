"""Unified spectrum panel with sweep controls, trace selection, and waterfall.

Replaces the old split Sweep tab + Live Graph tab with a single pane
that groups all spectrum-related controls on the left and the plot on
the right.  Supports scanraw binary streaming for higher resolution
and lower latency than the old per-trace text polling.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from pyqtgraph import ImageItem, GraphicsLayoutWidget
from pyqtgraph.colormap import get as get_colormap

from tsanet.controller.gui.stats_dialog import StatsDialog
from tsanet.controller.parse import parse_frequency
from tsanet.controller.rpc_client import RpcClient
from tsanet.controller.sweep_warning import sweep_mismatch_warning
from tsanet.controller.trace_hold import TraceHold

logger = logging.getLogger("tsanet.gui.spectrum")

#: Default dBm range for the spectrum plot.
DEFAULT_Y_MIN = -120.0
DEFAULT_Y_MAX = -20.0

WATERFALL_ROWS = 300

#: Up to 4 configurable trace slots, matching the device's own trace count.
TRACE_COLORS = ["#ff4444", "#44ff44", "#4488ff", "#ffcc00"]
TRACE_MODE_LABELS = {"Live": "live", "Min hold": "min", "Max hold": "max", "Average": "avg"}


class SpectrumPanel(QWidget):
    """Combined sweep-control + live-spectrum + optional waterfall widget."""

    def __init__(self, rpc: RpcClient | None = None, parent=None):
        super().__init__(parent)
        self._rpc = rpc
        self._subscription_active = False
        self._freqs: list[int] = []
        self._waterfall_data: Optional[np.ndarray] = None
        self._waterfall_rows = WATERFALL_ROWS
        self._trace_holds: list[TraceHold | None] = [None] * len(TRACE_COLORS)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # -- left panel: settings --------------------------------------------
        left = QWidget()
        left.setMaximumWidth(280)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(self._build_sweep_group())
        left_layout.addWidget(self._build_signal_group())
        left_layout.addWidget(self._build_traces_group())
        left_layout.addWidget(self._build_display_group())
        left_layout.addStretch()

        # -- right panel: spectrum + waterfall -------------------------------
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)

        self._glw = GraphicsLayoutWidget()
        self._spec_plot = self._glw.addPlot(row=0, col=0)
        self._spec_plot.setLabel("left", "dBm")
        self._spec_plot.setYRange(DEFAULT_Y_MIN, DEFAULT_Y_MAX)
        self._spec_plot.showGrid(x=True, y=True, alpha=0.3)
        self._spec_plot.hideButtons()
        self._curves: list = []

        self._wf_plot = self._glw.addPlot(row=1, col=0)
        self._wf_plot.setLabel("left", "Sweeps")
        self._wf_plot.setLabel("bottom", "Frequency", units="Hz")
        self._wf_plot.hideButtons()
        self._wf_img = ImageItem(axisOrder="col-major")
        self._wf_img.setLookupTable(get_colormap("viridis").getLookupTable())
        self._wf_img.setLevels((DEFAULT_Y_MIN, DEFAULT_Y_MAX))
        self._wf_plot.addItem(self._wf_img)
        self._wf_plot.hide()
        self._wf_plot.invertY(True)  # newest at top
        self._wf_plot.setXLink(self._spec_plot)

        self._glw.ci.layout.setRowStretchFactor(0, 3)
        self._glw.ci.layout.setRowStretchFactor(1, 1)

        right.addWidget(self._glw, 3)

        # Status bar
        self._status = QLabel("Set sweep range and press Start")
        self._status.setStyleSheet("color: #888")
        right.addWidget(self._status)

        layout.addWidget(left)
        layout.addLayout(right, 1)

        if rpc is not None:
            self._refresh_sweep_state()

    # -- sweep group --------------------------------------------------------

    def _build_sweep_group(self) -> QGroupBox:
        grp = QGroupBox("Sweep")
        form = QFormLayout(grp)

        self._sw_start = QLineEdit("100mhz")
        self._sw_start.setToolTip("Start frequency (e.g. 100mhz, 1.5ghz)")
        form.addRow("Start:", self._sw_start)

        self._sw_stop = QLineEdit("800mhz")
        self._sw_stop.setToolTip("Stop frequency (e.g. 800mhz, 1ghz)")
        form.addRow("Stop:", self._sw_stop)

        self._sw_pts = QSpinBox()
        self._sw_pts.setRange(51, 450)
        self._sw_pts.setValue(450)
        self._sw_pts.setToolTip("Number of sweep points")
        form.addRow("Points:", self._sw_pts)

        btn_row = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply_sweep)
        btn_row.addWidget(apply_btn)
        form.addRow(btn_row)

        return grp

    # -- signal group -------------------------------------------------------

    def _build_signal_group(self) -> QGroupBox:
        grp = QGroupBox("Signal")
        layout = QFormLayout(grp)

        self._lna_chk = QCheckBox("LNA (auto above 800 MHz)")
        layout.addRow(self._lna_chk)

        spur_row = QHBoxLayout()
        self._spur_cb = QComboBox()
        self._spur_cb.addItems(["off", "on", "auto"])
        self._spur_cb.setCurrentText("off")
        self._spur_cb.currentTextChanged.connect(self._set_spur)
        spur_row.addWidget(QLabel("Spur:"))
        spur_row.addWidget(self._spur_cb)
        layout.addRow(spur_row)

        return grp

    def _set_spur(self, mode: str) -> None:
        if self._rpc is None:
            return
        if mode == "on":
            self._rpc.call("signal", "enable_spur")
        elif mode == "off":
            self._rpc.call("signal", "disable_spur")
        elif mode == "auto":
            self._rpc.call("signal", "enable_auto_spur")

    # -- traces group ---------------------------------------------------------

    def _build_traces_group(self) -> QGroupBox:
        grp = QGroupBox("Traces")
        layout = QVBoxLayout(grp)

        self._trace_enable_cb: list[QCheckBox] = []
        self._trace_mode_cb: list[QComboBox] = []
        for i, color in enumerate(TRACE_COLORS):
            row = QHBoxLayout()
            enable = QCheckBox()
            enable.setChecked(i == 0)
            enable.setStyleSheet(f"QCheckBox::indicator {{ background-color: {color}; }}")
            enable.setToolTip(f"Show trace {i + 1} on the plot")
            row.addWidget(enable)

            mode_cb = QComboBox()
            mode_cb.addItems(list(TRACE_MODE_LABELS))
            mode_cb.setToolTip(
                "Live: raw scan.  Min/Max hold: running extremum since last "
                "reset.  Average: rolling mean over the last N sweeps."
            )
            row.addWidget(QLabel(f"{i + 1}:"))
            row.addWidget(mode_cb)
            layout.addLayout(row)

            self._trace_enable_cb.append(enable)
            self._trace_mode_cb.append(mode_cb)

        avg_row = QHBoxLayout()
        avg_row.addWidget(QLabel("Avg count:"))
        self._avg_window = QSpinBox()
        self._avg_window.setRange(2, 100)
        self._avg_window.setValue(4)
        self._avg_window.setToolTip("Number of sweeps averaged for 'Average' mode traces")
        avg_row.addWidget(self._avg_window)
        layout.addLayout(avg_row)

        reset_btn = QPushButton("Reset holds")
        reset_btn.setToolTip("Clear accumulated min/max/average state without stopping")
        reset_btn.clicked.connect(self._reset_holds)
        layout.addWidget(reset_btn)

        return grp

    def _reset_holds(self) -> None:
        for hold in self._trace_holds:
            if hold is not None:
                hold.reset()

    # -- display group ------------------------------------------------------

    def _build_display_group(self) -> QGroupBox:
        grp = QGroupBox("Display")
        layout = QFormLayout(grp)

        self._wf_chk = QCheckBox("Waterfall")
        self._wf_chk.toggled.connect(self._toggle_waterfall)
        layout.addRow(self._wf_chk)

        self._cmap_cb = QComboBox()
        self._cmap_cb.addItems(["viridis", "inferno", "plasma", "grayscale", "hot"])
        self._cmap_cb.currentTextChanged.connect(self._set_colormap)
        layout.addRow("Colormap:", self._cmap_cb)

        self._ref_spin = QSpinBox()
        self._ref_spin.setRange(25, 10000)
        self._ref_spin.setValue(150)
        self._ref_spin.setSuffix(" ms")
        self._ref_spin.setToolTip("Minimum interval between sweeps")
        layout.addRow("Interval:", self._ref_spin)

        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("Start")
        self._start_btn.setCheckable(True)
        self._start_btn.toggled.connect(self._toggle_stream)
        btn_row.addWidget(self._start_btn)
        layout.addRow(btn_row)

        stats_btn = QPushButton("Stats...")
        stats_btn.setToolTip(
            "Open the trace statistics dialog (average, median, min/max, "
            "channel power, occupied bandwidth, PAPR, flatness, field strength)"
        )
        stats_btn.clicked.connect(self._show_stats)
        layout.addRow(stats_btn)

        return grp

    def _show_stats(self) -> None:
        if self._rpc is None:
            self._status.setText("Connect to a hub first")
            return
        StatsDialog(self._rpc, self).exec()

    # -- RPC helpers --------------------------------------------------------

    def set_rpc(self, rpc: RpcClient) -> None:
        self._rpc = rpc
        self._refresh_sweep_state()

    def _call(self, domain: str, op: str, **args):
        if self._rpc is None:
            return None
        return self._rpc.call(domain, op, **args)

    # -- sweep actions ------------------------------------------------------

    def _apply_sweep(self) -> None:
        try:
            s = parse_frequency(self._sw_start.text())
            t = parse_frequency(self._sw_stop.text())
            p = self._sw_pts.value()
            self._call("sweep", "set_start_stop", start=s, stop=t, points=p)
            self._refresh_sweep_state(requested={"start": s, "stop": t, "points": p})
        except Exception as exc:
            self._status.setText(f"Error: {exc}")

    def _refresh_sweep_state(self, requested: dict | None = None) -> None:
        try:
            raw = str(self._call("sweep", "get"))
            parts = raw.split()
            if len(parts) >= 2:
                start = int(parts[0])
                stop = int(parts[1])
                points = int(parts[2]) if len(parts) > 2 else None
                self._sw_start.setText(str(start))
                self._sw_stop.setText(str(stop))
                if points is not None:
                    self._sw_pts.setValue(points)
                warning = sweep_mismatch_warning(requested, start, stop, points)
                if warning:
                    self._status.setText(warning)
                    QMessageBox.warning(self, "Sweep value adjusted", warning)
        except Exception:
            pass

    # -- streaming ----------------------------------------------------------

    def _toggle_stream(self, checked: bool) -> None:
        if checked:
            self._start_stream()
        else:
            self._stop_stream()

    def _start_stream(self) -> None:
        if self._rpc is None:
            return
        try:
            s = parse_frequency(self._sw_start.text())
            t = parse_frequency(self._sw_stop.text())
            pts = self._sw_pts.value()
        except Exception:
            self._status.setText("Invalid frequency")
            self._start_btn.setChecked(False)
            return

        # Enable LNA if checkbox is set
        if self._lna_chk.isChecked():
            self._rpc.call("signal", "enable_lna")

        # Set up one curve + hold per enabled trace slot (preserve waterfall).
        for _i, curve in self._curves:
            self._spec_plot.removeItem(curve)
        self._curves = []
        self._trace_holds = [None] * len(TRACE_COLORS)
        window = self._avg_window.value()
        for i, color in enumerate(TRACE_COLORS):
            if not self._trace_enable_cb[i].isChecked():
                continue
            mode = TRACE_MODE_LABELS[self._trace_mode_cb[i].currentText()]
            self._trace_holds[i] = TraceHold(mode, window=window)
            curve = self._spec_plot.plot([], [], pen=color, name=f"Trace {i + 1}")
            self._curves.append((i, curve))
        self._waterfall_data = None

        # Subscribe to scanraw
        self._rpc.on_event(self._on_scanraw_event)
        self._rpc.call(
            "scanraw",
            "subscribe",
            start=s,
            stop=t,
            pts=pts,
            interval=self._ref_spin.value() / 1000.0,
        )
        self._subscription_active = True
        self._status.setText(f"Streaming {s / 1e6:.1f}-{t / 1e6:.1f} MHz, {pts} pts")
        self._start_btn.setText("Stop")

    def _stop_stream(self) -> None:
        if self._rpc is not None:
            self._rpc.call("scanraw", "unsubscribe")
        self._subscription_active = False
        self._start_btn.setText("Start")
        self._status.setText("Stopped")

    # -- scanraw event handler ----------------------------------------------

    def _on_scanraw_event(self, event: object) -> None:
        data = event.data if hasattr(event, "data") else event
        if not isinstance(data, dict):
            return
        freqs = data.get("frequencies")
        level = data.get("level")

        # Initial frequencies frame
        if freqs and len(freqs) > 1 and not level:
            self._freqs = freqs
            self._waterfall_data = None
            return

        if not level or not self._freqs:
            return

        # Update curves — each slot's hold (live/min/max/avg) is computed
        # from the same raw scan, so a single scanraw stream drives every
        # trace mode without extra per-trace RPC round trips.
        n = min(len(self._freqs), len(level))
        raw = level[:n]
        for i, curve in self._curves:
            hold = self._trace_holds[i]
            assert hold is not None
            curve.setData(self._freqs[:n], hold.update(raw))

        # Update waterfall — PySDR pattern: col-major, roll axis=1,
        # fill column 0 with newest sweep.
        if self._wf_plot.isVisible():
            col = np.array(level[:n], dtype=np.float32)
            if self._waterfall_data is None:
                self._waterfall_data = -50.0 * np.ones((n, self._waterfall_rows), dtype=np.float32)
            self._waterfall_data = np.roll(self._waterfall_data, 1, axis=1)
            self._waterfall_data[:, 0] = col
            self._wf_img.setImage(self._waterfall_data, autoLevels=False)
            self._wf_img.setRect(
                self._freqs[0], 0, self._freqs[-1] - self._freqs[0], self._waterfall_rows
            )

    # -- waterfall ----------------------------------------------------------

    def _toggle_waterfall(self, visible: bool) -> None:
        self._wf_plot.setVisible(visible)
        if visible:
            self._waterfall_data = None

    def _set_colormap(self, name: str) -> None:
        cmap = get_colormap(name)
        self._wf_img.setLookupTable(cmap.getLookupTable())

    # -- cleanup ------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._subscription_active:
            self._stop_stream()
        super().closeEvent(event)
