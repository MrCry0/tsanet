"""Live signal graph panel with subscription push."""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from tsanet.controller.rpc_client import RpcClient
from tsanet.device.model import VALID_CALC
from tsanet.protocol.messages import Event


class _EventBridge(QObject):
    """Receives events from the reader thread and forwards to the GUI thread."""

    arrived = Signal(dict)


class LiveGraphPanel(QWidget):
    def __init__(self, rpc: RpcClient, parent=None):
        super().__init__(parent)
        self._rpc = rpc
        self._running = False
        self._frequencies: list[int] = []

        self._bridge = _EventBridge()
        self._bridge.arrived.connect(self._on_event)

        self._plot = pg.PlotWidget()
        self._plot.setLabel("bottom", "Frequency", "Hz")
        self._plot.setLabel("left", "Amplitude", "dBm")
        self._plot.showGrid(x=True, y=True)

        line_group = QGroupBox("Lines")
        self._line_calcs: list[QComboBox] = []
        self._line_checks: list[QCheckBox] = []
        defaults = ["minh", "aver4", "maxh"]
        for i in range(3):
            chk = QCheckBox(f"Line {i + 1}")
            chk.setChecked(True)
            chk.setToolTip(f"Enable trace line {i + 1} in the live graph")
            calc = QComboBox()
            calc.addItems(sorted(VALID_CALC))
            calc.setCurrentText(defaults[i])
            calc.setToolTip(
                "Trace calculation mode: minh (min-hold), maxh (max-hold), "
                "aver4 (4-sample average), off, write, view, blank"
            )
            line_layout = QFormLayout()
            line_layout.addRow(chk, calc)
            line_group.setLayout(line_layout)
            self._line_checks.append(chk)
            self._line_calcs.append(calc)

        mode_group = QGroupBox("Update")
        self._max_speed = QRadioButton("Max speed")
        self._max_speed.setChecked(True)
        self._max_speed.setToolTip("Update the graph as fast as the device produces sweeps")
        self._fixed = QRadioButton("Fixed interval")
        self._fixed.setToolTip("Update the graph at a fixed rate (0.1 to 60 seconds)")
        self._interval = QDoubleSpinBox()
        self._interval.setRange(0.1, 60)
        self._interval.setValue(0.5)
        self._interval.setSuffix(" sec")
        self._interval.setEnabled(False)
        self._interval.setToolTip("Fixed update interval in seconds")
        self._fixed.toggled.connect(lambda on: self._interval.setEnabled(on))

        mode_layout = QVBoxLayout(mode_group)
        mode_layout.addWidget(self._max_speed)
        h = QHBoxLayout()
        h.addWidget(self._fixed)
        h.addWidget(self._interval)
        mode_layout.addLayout(h)

        self._start_btn = QPushButton("Start")
        self._start_btn.setToolTip("Enable selected traces on the device and start live streaming")
        self._start_btn.clicked.connect(self._start)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setToolTip("Stop live streaming and unsubscribe")
        self._stop_btn.clicked.connect(self._stop)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self._start_btn)
        btn_layout.addWidget(self._stop_btn)

        left = QVBoxLayout()
        left.addWidget(line_group)
        left.addWidget(mode_group)
        left.addLayout(btn_layout)
        left.addStretch()
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setMaximumWidth(250)

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(left_w)
        main_layout.addWidget(self._plot)

    def _start(self):
        ids = [i + 1 for i in range(3) if self._line_checks[i].isChecked()]
        if not ids:
            return

        for i in range(3):
            if not self._line_checks[i].isChecked():
                continue
            tid = i + 1
            calc = self._line_calcs[i].currentText()
            try:
                self._rpc.call("trace", "enable", id=tid)
                if calc != "off":
                    self._rpc.call("trace", "enable_calc", id=tid, calc=calc)
            except Exception:
                pass

        interval = None if self._max_speed.isChecked() else self._interval.value()
        self._rpc.call("trace", "subscribe", ids=ids, interval=interval)

        self._plot.clear()
        self._curves = []
        colors = [(255, 100, 100), (100, 255, 100), (100, 100, 255)]
        for i in range(3):
            if self._line_checks[i].isChecked():
                curve = self._plot.plot([], [], pen=pg.mkPen(color=colors[i], width=1.5))
                self._curves.append(curve)
                self._line_checks[i].setEnabled(False)
                self._line_calcs[i].setEnabled(False)
            else:
                self._curves.append(None)

        self._running = True
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._rpc.on_event(self._on_reader_event)

    def _stop(self):
        self._running = False
        self._rpc.on_event(None)
        try:
            self._rpc.call("trace", "unsubscribe")
        except Exception:
            pass
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        for i in range(3):
            self._line_checks[i].setEnabled(True)
            self._line_calcs[i].setEnabled(True)

    def _on_reader_event(self, event: Event):
        """Called from the reader thread — bridge to GUI thread."""
        if event.domain == "trace" and event.op == "update":
            self._bridge.arrived.emit(event.data if isinstance(event.data, dict) else {})

    @Slot(dict)
    def _on_event(self, data: dict):
        if not self._running:
            return
        freqs = data.get("frequencies")
        if freqs:
            self._frequencies = freqs
        traces = data.get("traces", {})
        for i in range(3):
            curve = self._curves[i]
            if curve is not None:
                tid = str(i + 1)
                if tid in traces:
                    curve.setData(self._frequencies, traces[tid])
