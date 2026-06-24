"""Live signal graph panel with subscription push (brief 6.3, 10)."""

from __future__ import annotations

import pyqtgraph as pg
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


class LiveGraphPanel(QWidget):
    def __init__(self, rpc: RpcClient, parent=None):
        super().__init__(parent)
        self._rpc = rpc
        self._running = False
        self._frequencies: list[int] = []

        self._plot = pg.PlotWidget()
        self._plot.setLabel("bottom", "Frequency", "Hz")
        self._plot.setLabel("left", "Amplitude", "dBm")
        self._plot.showGrid(x=True, y=True)

        # --- line config ---
        line_group = QGroupBox("Lines")
        line_layout = QFormLayout()
        self._line_calcs: list[QComboBox] = []
        self._line_checks: list[QCheckBox] = []
        defaults = ["minh", "aver4", "maxh"]
        for i in range(3):
            chk = QCheckBox(f"Line {i + 1}")
            chk.setChecked(True)
            calc = QComboBox()
            calc.addItems(sorted(VALID_CALC))
            calc.setCurrentText(defaults[i])
            line_layout.addRow(chk, calc)
            self._line_checks.append(chk)
            self._line_calcs.append(calc)
        line_group.setLayout(line_layout)

        # --- update mode ---
        mode_group = QGroupBox("Update")
        self._max_speed = QRadioButton("Max speed")
        self._max_speed.setChecked(True)
        self._fixed = QRadioButton("Fixed interval")
        self._interval = QDoubleSpinBox()
        self._interval.setRange(0.1, 60)
        self._interval.setValue(0.5)
        self._interval.setSuffix(" sec")
        self._interval.setEnabled(False)
        self._fixed.toggled.connect(lambda on: self._interval.setEnabled(on))

        mode_layout = QVBoxLayout(mode_group)
        mode_layout.addWidget(self._max_speed)
        h = QHBoxLayout()
        h.addWidget(self._fixed)
        h.addWidget(self._interval)
        mode_layout.addLayout(h)

        # --- controls ---
        self._start_btn = QPushButton("Start")
        self._start_btn.clicked.connect(self._start)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self._start_btn)
        btn_layout.addWidget(self._stop_btn)

        # --- layout ---
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
        self._rpc.on_event(self._on_event)

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

    def _on_event(self, event: Event):
        if not self._running or event.domain != "trace" or event.op != "update":
            return
        data = event.data
        if not isinstance(data, dict):
            return
        freqs = data.get("frequencies")
        if freqs:
            self._frequencies = freqs
        traces = data.get("traces", {})
        curve_idx = 0
        for i in range(3):
            if self._curves[i] is not None:
                tid = i + 1
                if str(tid) in traces:
                    self._curves[i].setData(self._frequencies, traces[str(tid)])
                curve_idx += 1
