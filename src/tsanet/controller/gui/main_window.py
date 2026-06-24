"""Main window for the controller GUI (brief 10)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tsanet.controller.gui.capture_viewer import CaptureViewer
from tsanet.controller.gui.connection_dialog import ConnectionDialog
from tsanet.controller.gui.device_panel import DevicePanel
from tsanet.controller.gui.live_graph import LiveGraphPanel
from tsanet.controller.gui.stats_dialog import StatsDialog
from tsanet.controller.parse import parse_frequency
from tsanet.controller.rpc_client import RpcClient


class MainWindow(QMainWindow):
    def __init__(self, config=None):
        super().__init__()
        self.setWindowTitle("tsanet Controller")
        self.setMinimumSize(900, 600)
        self._rpc: RpcClient | None = None

        self._status = QStatusBar()
        self.setStatusBar(self._status)

        tabs = QTabWidget()
        tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs = tabs
        self._device_panel = QWidget()  # placeholder
        self._sweep_panel = self._build_sweep_panel()
        self._trace_panel = self._build_trace_panel()
        self._capture_viewer = QWidget()  # placeholder
        self._live_graph = QWidget()  # placeholder

        self._SWEEP_TAB = 1

        tabs.addTab(self._device_panel, "Devices")
        tabs.addTab(self._sweep_panel, "Sweep")
        tabs.addTab(self._trace_panel, "Trace")
        tabs.addTab(self._capture_viewer, "Capture")
        tabs.addTab(self._live_graph, "Live Graph")
        self.setCentralWidget(tabs)

        if config:
            self._connect(config)
        else:
            self._show_connection_dialog()

    # -- connection --------------------------------------------------------

    def _show_connection_dialog(self):
        dlg = ConnectionDialog(self)
        if dlg.exec():
            self._connect(dlg.config())
        else:
            from PySide6.QtWidgets import QApplication
            QApplication.quit()

    def _connect(self, config):
        try:
            old = self._rpc
            self._rpc = RpcClient(config)
            self._rpc.connect()
            if old:
                old.close()
            self._status.showMessage("Connected")
        except Exception as exc:
            QMessageBox.critical(self, "Connection Error", str(exc))
            return

        # Rebuild device-dependent widgets
        central = self.centralWidget()
        if isinstance(central, QTabWidget):
            self._device_panel = DevicePanel(self._rpc)
            central.removeTab(0)
            central.insertTab(0, self._device_panel, "Devices")

            self._capture_viewer = CaptureViewer(self._rpc)
            central.removeTab(3)
            central.insertTab(3, self._capture_viewer, "Capture")

            self._live_graph = LiveGraphPanel(self._rpc)
            central.removeTab(4)
            central.insertTab(4, self._live_graph, "Live Graph")

            self._refresh_sweep_status()

    def _on_tab_changed(self, index):
        if index == self._SWEEP_TAB and self._rpc is not None:
            self._refresh_sweep_status()

    # -- sweep panel -------------------------------------------------------

    def _build_sweep_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        # Range group
        range_group = QGroupBox("Range")
        form = QFormLayout()
        self._sw_start = QLineEdit("0")
        self._sw_stop = QLineEdit("800mhz")
        self._sw_points = QLineEdit("450")
        form.addRow("Start:", self._sw_start)
        form.addRow("Stop:", self._sw_stop)
        form.addRow("Points:", self._sw_points)
        range_group.setLayout(form)

        # Center / Span / CW
        ctrl = QGroupBox("Control")
        ctrl_layout = QFormLayout()
        self._sw_center = QLineEdit()
        self._sw_span = QLineEdit()
        self._sw_cw = QLineEdit()
        ctrl_layout.addRow("Center:", self._sw_center)
        ctrl_layout.addRow("Span:", self._sw_span)
        ctrl_layout.addRow("CW:", self._sw_cw)
        ctrl.setLayout(ctrl_layout)

        # Buttons
        btn = QHBoxLayout()
        apply_btn = QPushButton("Apply Range")
        apply_btn.clicked.connect(self._apply_sweep_range)
        center_btn = QPushButton("Set Center")
        center_btn.clicked.connect(self._apply_sweep_center)
        span_btn = QPushButton("Set Span")
        span_btn.clicked.connect(self._apply_sweep_span)
        cw_btn = QPushButton("Set CW")
        cw_btn.clicked.connect(self._apply_sweep_cw)
        btn.addWidget(apply_btn)
        btn.addWidget(center_btn)
        btn.addWidget(span_btn)
        btn.addWidget(cw_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(lambda: self._refresh_sweep_status())

        # Status
        self._sweep_status = QLabel("")

        layout.addWidget(range_group)
        layout.addWidget(ctrl)
        layout.addLayout(btn)
        layout.addWidget(refresh_btn)
        layout.addWidget(self._sweep_status)
        layout.addStretch()
        return w

    def _rpc_or_none(self):
        return self._rpc

    def _call(self, domain, op, **args):
        rpc = self._rpc
        if rpc is None:
            QMessageBox.warning(self, "Not connected", "Connect to a hub first")
            raise RuntimeError("not connected")
        return rpc.call(domain, op, **args)

    def _apply_sweep_range(self):
        try:
            s = parse_frequency(self._sw_start.text())
            t = parse_frequency(self._sw_stop.text())
            p = int(self._sw_points.text()) if self._sw_points.text() else None
            self._call("sweep", "set_start_stop", start=s, stop=t, points=p)
            self._refresh_sweep_status()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _apply_sweep_center(self):
        try:
            if not self._sw_center.text():
                return
            hz = parse_frequency(self._sw_center.text())
            self._call("sweep", "set_center", hz=hz)
            self._refresh_sweep_status()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _apply_sweep_span(self):
        try:
            if not self._sw_span.text():
                return
            hz = parse_frequency(self._sw_span.text())
            self._call("sweep", "set_span", hz=hz)
            self._refresh_sweep_status()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _apply_sweep_cw(self):
        try:
            if not self._sw_cw.text():
                return
            hz = parse_frequency(self._sw_cw.text())
            self._call("sweep", "set_cw", hz=hz)
            self._refresh_sweep_status()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _refresh_sweep_status(self):
        try:
            raw = str(self._call("sweep", "get"))
            parts = raw.split()
            if len(parts) >= 2:
                s = int(parts[0])
                t = int(parts[1])
                c = (s + t) // 2
                p = int(parts[2]) if len(parts) > 2 else None
                # Update the input fields to reflect actual device state.
                self._sw_start.setText(str(s))
                self._sw_stop.setText(str(t))
                self._sw_center.setText(str(c))
                self._sw_span.setText(str(t - s))
                if p is not None:
                    self._sw_points.setText(str(p))
                # Status bar text.
                text = f"Start: {_fmt(s)}  Stop: {_fmt(t)}  Center: {_fmt(c)}"
                if p:
                    text += f"  Points: {p}"
                self._sweep_status.setText(text)
        except Exception:
            self._sweep_status.setText("(readback failed)")

    # -- trace panel -------------------------------------------------------

    def _build_trace_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        group = QGroupBox("Trace")
        form = QFormLayout()
        self._trace_id = QLineEdit("1")
        self._trace_calc = QLineEdit()
        form.addRow("ID:", self._trace_id)
        form.addRow("Calc:", self._trace_calc)

        btn = QHBoxLayout()
        on_btn = QPushButton("On")
        on_btn.clicked.connect(lambda: self._trace_cmd("enable"))
        off_btn = QPushButton("Off")
        off_btn.clicked.connect(lambda: self._trace_cmd("disable"))
        calc_btn = QPushButton("Set Calc")
        calc_btn.clicked.connect(
            lambda: self._trace_cmd("enable_calc", calc=self._trace_calc.text() or "off")
        )
        # actually need to not send empty calc
        btn.addWidget(on_btn)
        btn.addWidget(off_btn)
        btn.addWidget(calc_btn)

        group.setLayout(form)
        layout.addWidget(group)
        layout.addLayout(btn)

        # stats button
        stats_btn = QPushButton("Trace Stats...")
        stats_btn.clicked.connect(self._open_stats)
        layout.addWidget(stats_btn)
        layout.addStretch()

        return w

    def _trace_cmd(self, op, **extra):
        try:
            tid = int(self._trace_id.text())
            self._call("trace", op, id=tid, **extra)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _open_stats(self):
        if self._rpc is None:
            QMessageBox.warning(self, "Not connected", "Connect first")
            return
        dlg = StatsDialog(self._rpc, self)
        dlg.exec()


def _fmt(hz: int) -> str:
    if hz >= 1_000_000_000:
        return f"{hz / 1e9:.3f} GHz"
    if hz >= 1_000_000:
        return f"{hz / 1e6:.3f} MHz"
    if hz >= 1_000:
        return f"{hz / 1e3:.3f} kHz"
    return f"{hz} Hz"
