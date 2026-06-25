"""Main window for the controller GUI."""

from __future__ import annotations

import logging
from logging import LogRecord

from PySide6.QtCore import Qt, QObject, Signal, Slot
from PySide6.QtWidgets import (
    QDockWidget,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tsanet import __version__
from tsanet.controller.gui.capture_viewer import CaptureViewer
from tsanet.controller.gui.connection_dialog import ConnectionDialog
from tsanet.controller.gui.device_panel import DevicePanel
from tsanet.controller.gui.live_graph import LiveGraphPanel
from tsanet.controller.gui.stats_dialog import StatsDialog
from tsanet.controller.parse import parse_frequency
from tsanet.controller.rpc_client import RpcClient


class _LogBridge(QObject):
    """Bridges logging records from any thread to the GUI thread."""

    record_ready = Signal(str)


class _LogHandler(logging.Handler):
    """Sends log records to a QPlainTextEdit via a signal bridge."""

    def __init__(self, bridge: _LogBridge, level: int = logging.NOTSET) -> None:
        super().__init__(level)
        self._bridge = bridge

    def emit(self, record: LogRecord) -> None:
        self._bridge.record_ready.emit(self.format(record))


class MainWindow(QMainWindow):
    def __init__(self, config=None):
        super().__init__()
        self.setWindowTitle("tsanet Controller")
        self.setMinimumSize(900, 600)
        self._rpc: RpcClient | None = None

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Not connected — open File > Connect or restart to connect")

        self._build_log_dock()
        self._build_menu()

        tabs = QTabWidget()
        tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs = tabs
        self._device_panel = QWidget()
        self._sweep_panel = self._build_sweep_panel()
        self._trace_panel = self._build_trace_panel()
        self._capture_viewer = QWidget()
        self._live_graph = QWidget()

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

    # -- log dock ------------------------------------------------------------

    def _build_log_dock(self) -> None:
        self._log_widget = QPlainTextEdit()
        self._log_widget.setReadOnly(True)
        self._log_widget.setMaximumBlockCount(2000)
        self._log_widget.setTabChangesFocus(False)
        self._log_widget.setStyleSheet(
            "QPlainTextEdit { font-family: monospace; font-size: 11px; }"
        )

        dock = QDockWidget("Log", self)
        dock.setWidget(self._log_widget)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        dock.hide()
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self._log_dock = dock

        bridge = _LogBridge()
        bridge.record_ready.connect(self._append_log)

        handler = _LogHandler(bridge)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)-5s] %(name)s: %(message)s", "%H:%M:%S")
        )
        handler.setLevel(logging.INFO)
        logging.getLogger("tsanet").addHandler(handler)
        self._log_handler = handler

    @Slot(str)
    def _append_log(self, text: str) -> None:
        self._log_widget.appendPlainText(text)

    def _toggle_log(self) -> None:
        self._log_dock.setVisible(not self._log_dock.isVisible())
        if self._log_dock.isVisible():
            self._log_handler.setLevel(logging.DEBUG)
        else:
            self._log_handler.setLevel(logging.INFO)

    # -- menu ---------------------------------------------------------------

    def _build_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")
        reconnect = file_menu.addAction("&Connect...")
        reconnect.triggered.connect(self._show_connection_dialog)
        file_menu.addSeparator()
        quit_act = file_menu.addAction("&Quit")
        quit_act.triggered.connect(self.close)

        view_menu = menu.addMenu("&View")
        log_act = view_menu.addAction("&Log")
        log_act.setCheckable(True)
        log_act.triggered.connect(self._toggle_log)

        help_menu = menu.addMenu("&Help")
        help_menu.addAction("Usage &Guide", self._show_guide)
        help_menu.addAction("&About tsanet...", self._show_about)

    def _show_about(self):
        QMessageBox.about(
            self,
            "About tsanet",
            (
                f"<b>tsanet {__version__}</b>"
                "<br>Network control suite for tinySA spectrum analyzers."
                "<br><br>"
                "Components:"
                "<ul>"
                "<li><tt>tsanet-hub</tt> — device host (USB serial)</li>"
                "<li><tt>tsanet-ctl</tt> — command-line controller</li>"
                "<li><tt>tsanet-gui</tt> — graphical controller</li>"
                "</ul>"
                "License: GPL-2.0-only"
                "<br>"
                "<a href='https://github.com/MrCry0/tsanet'>github.com/MrCry0/tsanet</a>"
            ),
        )

    def _show_guide(self):
        QMessageBox.information(
            self,
            "Usage Guide",
            (
                "<b>Getting started</b>"
                "<ol>"
                "<li>Start <tt>tsanet-hub</tt> on the machine with tinySA units attached.</li>"
                "<li>Open File > Connect and enter the hub's address and port.</li>"
                "<li>Use the Devices tab to select which tinySA to control.</li>"
                "</ol>"
                "<b>Tabs</b>"
                "<ul>"
                "<li><b>Devices</b> — list attached units; click one to take control.</li>"
                "<li><b>Sweep</b> — set start/stop/center/span/CW; fields refresh "
                "on activation.</li>"
                "<li><b>Trace</b> — enable/disable trace modes and open statistics.</li>"
                "<li><b>Capture</b> — fetch, save, or copy the device screenshot.</li>"
                "<li><b>Live Graph</b> — real-time spectrum with up to 3 trace lines.</li>"
                "</ul>"
                "<b>Sweep value adjustment</b>"
                "<br>If the device clamps a requested value (e.g. points capped at "
                "the device maximum), a warning dialog will appear and the actual "
                "applied values will be shown."
                "<br><br>"
                "<b>Trace statistics</b>"
                "<br>Open with the Trace Stats button on the Trace tab. "
                "Select a frequency sub-range and a display unit. "
                "Available metrics: average power, median, min/max with "
                "frequencies, channel power, occupied bandwidth (99% OBW), "
                "PAPR, flatness, and field strength (with antenna factor)."
                "<br><br>"
                "<b>Keyboard shortcuts</b>"
                "<ul>"
                "<li><tt>Ctrl+Q</tt> — Quit</li>"
                "</ul>"
                "<b>Configuration files</b>"
                "<br>Settings are loaded from "
                "<tt>~/.config/tsanet/controller.yaml</tt> "
                "and overridden by command-line flags when launching "
                "<tt>tsanet-gui</tt>."
            ),
        )

    # -- connection ---------------------------------------------------------

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
        if self._SWEEP_TAB == index and self._rpc is not None:
            self._refresh_sweep_status()
            self._status.showMessage("Sweep tab — set range, center, span, or CW")
        elif index == 0 and self._rpc is not None:
            self._status.showMessage("Devices tab — click a device to select it")
        elif index == 2 and self._rpc is not None:
            self._status.showMessage("Trace tab — enable traces and open statistics")
        elif index == 3 and self._rpc is not None:
            self._status.showMessage("Capture tab — fetch a screenshot from the device")
        elif index == 4 and self._rpc is not None:
            self._status.showMessage(
                "Live Graph — configurable trace lines, max-speed or fixed-interval updates"
            )

    # -- sweep panel --------------------------------------------------------

    def _build_sweep_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        range_group = QGroupBox("Range")
        form = QFormLayout()
        self._sw_start = QLineEdit("0")
        self._sw_start.setToolTip("Sweep start frequency (e.g. 100mhz, 1.5ghz)")
        self._sw_start.setPlaceholderText("e.g. 100mhz")
        self._sw_stop = QLineEdit("800mhz")
        self._sw_stop.setToolTip("Sweep stop frequency (e.g. 800mhz, 1ghz)")
        self._sw_stop.setPlaceholderText("e.g. 800mhz")
        self._sw_points = QLineEdit("450")
        self._sw_points.setToolTip(
            "Number of sweep points (device maximum is model-dependent, typically 450)"
        )
        form.addRow("Start:", self._sw_start)
        form.addRow("Stop:", self._sw_stop)
        form.addRow("Points:", self._sw_points)
        range_group.setLayout(form)

        ctrl = QGroupBox("Control")
        ctrl_layout = QFormLayout()
        self._sw_center = QLineEdit()
        self._sw_center.setToolTip("Center frequency — sets start/stop around this value")
        self._sw_center.setPlaceholderText("e.g. 433.92mhz")
        self._sw_span = QLineEdit()
        self._sw_span.setToolTip("Span width — sets start/stop symmetrically around center")
        self._sw_span.setPlaceholderText("e.g. 200mhz")
        self._sw_cw = QLineEdit()
        self._sw_cw.setPlaceholderText("e.g. 433.92mhz")
        self._sw_cw.setToolTip("Continuous-wave (zero-span) frequency")
        ctrl_layout.addRow("Center:", self._sw_center)
        ctrl_layout.addRow("Span:", self._sw_span)
        ctrl_layout.addRow("CW:", self._sw_cw)
        ctrl.setLayout(ctrl_layout)

        btn = QHBoxLayout()
        apply_btn = QPushButton("Apply Range")
        apply_btn.setToolTip("Set sweep start, stop, and points on the device")
        apply_btn.clicked.connect(self._apply_sweep_range)
        center_btn = QPushButton("Set Center")
        center_btn.setToolTip("Set center frequency (updates start/stop)")
        center_btn.clicked.connect(self._apply_sweep_center)
        span_btn = QPushButton("Set Span")
        span_btn.setToolTip("Set span width (updates start/stop symmetrically)")
        span_btn.clicked.connect(self._apply_sweep_span)
        cw_btn = QPushButton("Set CW")
        cw_btn.setToolTip("Set continuous-wave (zero-span) frequency")
        cw_btn.clicked.connect(self._apply_sweep_cw)
        btn.addWidget(apply_btn)
        btn.addWidget(center_btn)
        btn.addWidget(span_btn)
        btn.addWidget(cw_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Read current sweep state back from the device")
        refresh_btn.clicked.connect(lambda: self._refresh_sweep_status())

        self._sweep_status = QLabel("")
        self._sweep_status.setWordWrap(True)

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
            self._refresh_sweep_status(requested={"start": s, "stop": t, "points": p})
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _apply_sweep_center(self):
        try:
            if not self._sw_center.text():
                return
            hz = parse_frequency(self._sw_center.text())
            self._call("sweep", "set_center", hz=hz)
            self._refresh_sweep_status(requested={"center": hz})
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _apply_sweep_span(self):
        try:
            if not self._sw_span.text():
                return
            hz = parse_frequency(self._sw_span.text())
            self._call("sweep", "set_span", hz=hz)
            self._refresh_sweep_status(requested={"span": hz})
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _apply_sweep_cw(self):
        try:
            if not self._sw_cw.text():
                return
            hz = parse_frequency(self._sw_cw.text())
            self._call("sweep", "set_cw", hz=hz)
            self._refresh_sweep_status(requested={"cw": hz})
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    @staticmethod
    def _sweep_mismatch_warning(requested, s, t, p) -> str | None:
        """Describe any requested sweep value the device did not apply as-is.

        The device can silently clamp a request (e.g. a 900-point request
        capped to its 450-point maximum) without returning an error.
        """
        if not requested:
            return None
        actual = {
            "start": s,
            "stop": t,
            "points": p,
            "center": (s + t) // 2,
            "span": t - s,
            "cw": s,
        }
        mismatches = []
        for key, want in requested.items():
            got = actual.get(key)
            if want is None or got is None or want == got:
                continue
            shown = str(want) if key == "points" else _fmt(want)
            shown_got = str(got) if key == "points" else _fmt(got)
            mismatches.append(f"{key} {shown} -> {shown_got}")
        if not mismatches:
            return None
        return "device adjusted: " + ", ".join(mismatches)

    def _refresh_sweep_status(self, requested: dict | None = None):
        try:
            raw = str(self._call("sweep", "get"))
            parts = raw.split()
            if len(parts) >= 2:
                s = int(parts[0])
                t = int(parts[1])
                c = (s + t) // 2
                p = int(parts[2]) if len(parts) > 2 else None
                self._sw_start.setText(str(s))
                self._sw_stop.setText(str(t))
                self._sw_center.setText(str(c))
                self._sw_span.setText(str(t - s))
                if p is not None:
                    self._sw_points.setText(str(p))
                text = f"Start: {_fmt(s)}  Stop: {_fmt(t)}  Center: {_fmt(c)}"
                if p:
                    text += f"  Points: {p}"
                warning = self._sweep_mismatch_warning(requested, s, t, p)
                if warning:
                    text += f"  WARNING: {warning}"
                    QMessageBox.warning(self, "Sweep value adjusted", warning)
                self._sweep_status.setText(text)
                self._status.showMessage(text)
        except Exception:
            self._sweep_status.setText("(readback failed)")

    # -- trace panel --------------------------------------------------------

    def _build_trace_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        group = QGroupBox("Trace")
        form = QFormLayout()
        self._trace_id = QLineEdit("1")
        self._trace_id.setToolTip("Trace channel number (1-4 on tinySA Ultra)")
        self._trace_id.setPlaceholderText("1")
        self._trace_calc = QLineEdit()
        self._trace_calc.setToolTip("Calculation mode: minh, maxh, aver4, off, etc.")
        self._trace_calc.setPlaceholderText("e.g. minh")
        form.addRow("ID:", self._trace_id)
        form.addRow("Calc:", self._trace_calc)

        btn = QHBoxLayout()
        on_btn = QPushButton("On")
        on_btn.setToolTip("Enable the selected trace")
        on_btn.clicked.connect(lambda: self._trace_cmd("enable"))
        off_btn = QPushButton("Off")
        off_btn.setToolTip("Disable the selected trace")
        off_btn.clicked.connect(lambda: self._trace_cmd("disable"))
        calc_btn = QPushButton("Set Calc")
        calc_btn.setToolTip("Apply the calculation mode to the selected trace")
        calc_btn.clicked.connect(
            lambda: self._trace_cmd("enable_calc", calc=self._trace_calc.text() or "off")
        )
        btn.addWidget(on_btn)
        btn.addWidget(off_btn)
        btn.addWidget(calc_btn)

        group.setLayout(form)
        layout.addWidget(group)
        layout.addLayout(btn)

        stats_btn = QPushButton("Trace Stats...")
        stats_btn.setToolTip(
            "Open statistics dialog: average, median, min/max, channel power, "
            "occupied bandwidth, PAPR, flatness, field strength"
        )
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
