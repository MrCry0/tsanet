"""Main window for the controller GUI."""

from __future__ import annotations

import logging
from logging import LogRecord

from PySide6.QtCore import Qt, QObject, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFormLayout,
    QGridLayout,
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
from tsanet.controller.config import DEFAULT_CONFIG_PATH
from tsanet.controller.gui.capture_viewer import CaptureViewer
from tsanet.controller.gui.connection_dialog import ConnectionDialog
from tsanet.controller.gui.device_panel import DevicePanel
from tsanet.controller.gui.live_graph import LiveGraphPanel
from tsanet.controller.parse import parse_frequency
from tsanet.controller.rpc_client import RpcClient
from tsanet.device.model import VALID_CALC


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
    def __init__(self, config=None, config_path=None):
        super().__init__()
        self.setWindowTitle("tsanet Controller")
        self.setMinimumSize(900, 600)
        self._rpc: RpcClient | None = None
        self._config_path = config_path

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
        self._live_graph_panel = self._build_live_graph_panel()
        self._capture_viewer = QWidget()

        self._SWEEP_TAB = 1
        self._GRAPH_TAB = 2

        tabs.addTab(self._device_panel, "Devices")
        tabs.addTab(self._sweep_panel, "Sweep")
        tabs.addTab(self._live_graph_panel, "Live Graph")
        tabs.addTab(self._capture_viewer, "Capture")
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
        from tsanet.controller.config import ControllerConfig

        dlg = ConnectionDialog(config_path=self._config_path, parent=self)

        # Pre-populate from an existing config file.
        try:
            cfg = ControllerConfig.load(self._config_path or DEFAULT_CONFIG_PATH)
            dlg._mode.setCurrentText(cfg.network.mode)
            dlg._transport.setCurrentText(cfg.network.transport)
            dlg._address.setText(cfg.network.address)
            if cfg.network.port is not None:
                dlg._port.setValue(cfg.network.port)
            dlg._sec_mode.setCurrentText(cfg.security.mode)
            if cfg.security.token:
                dlg._token.setText(cfg.security.token)
        except Exception:
            pass

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

            self._live_graph_widget = LiveGraphPanel(self._rpc)
            self._live_graph_widget.set_data_callback(self._on_subscription_data)
            self._live_graph_container.layout().addWidget(self._live_graph_widget.graph)

            self._refresh_sweep_status()
            self._refresh_trace_state()

    def _on_tab_changed(self, index):
        if self._SWEEP_TAB == index and self._rpc is not None:
            self._refresh_sweep_status()
            self._status.showMessage("Sweep tab — set range, center, span, or CW")
        elif index == 0 and self._rpc is not None:
            self._status.showMessage("Devices tab — click a device to select it")
        elif self._GRAPH_TAB == index and self._rpc is not None:
            self._refresh_trace_state()
            self._status.showMessage("Live Graph — toggle traces, set calc, graph, or stats")
        elif index == 3 and self._rpc is not None:
            self._status.showMessage("Capture tab — fetch a screenshot from the device")

    # -- sweep panel --------------------------------------------------------

    def _build_sweep_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        range_group = QGroupBox("Range  (press Enter to apply)")
        form = QFormLayout()
        self._sw_start = QLineEdit("0")
        self._sw_start.setToolTip("Sweep start frequency (e.g. 100mhz, 1.5ghz)")
        self._sw_start.setPlaceholderText("e.g. 100mhz")
        self._sw_start.returnPressed.connect(self._apply_sweep_range)
        self._sw_stop = QLineEdit("800mhz")
        self._sw_stop.setToolTip("Sweep stop frequency (e.g. 800mhz, 1ghz)")
        self._sw_stop.setPlaceholderText("e.g. 800mhz")
        self._sw_stop.returnPressed.connect(self._apply_sweep_range)
        self._sw_points = QLineEdit("450")
        self._sw_points.setToolTip(
            "Number of sweep points (device maximum is model-dependent, typically 450)"
        )
        self._sw_points.returnPressed.connect(self._apply_sweep_range)
        form.addRow("Start:", self._sw_start)
        form.addRow("Stop:", self._sw_stop)
        form.addRow("Points:", self._sw_points)
        range_group.setLayout(form)

        ctrl = QGroupBox("Control  (press Enter to apply)")
        ctrl_layout = QFormLayout()
        self._sw_center = QLineEdit()
        self._sw_center.setToolTip("Center frequency — sets start/stop around this value")
        self._sw_center.setPlaceholderText("e.g. 433.92mhz")
        self._sw_center.returnPressed.connect(self._apply_sweep_center)
        self._sw_span = QLineEdit()
        self._sw_span.setToolTip("Span width — sets start/stop symmetrically around center")
        self._sw_span.setPlaceholderText("e.g. 200mhz")
        self._sw_span.returnPressed.connect(self._apply_sweep_span)
        self._sw_cw = QLineEdit()
        self._sw_cw.setPlaceholderText("e.g. 433.92mhz")
        self._sw_cw.setToolTip("Continuous-wave (zero-span) frequency")
        self._sw_cw.returnPressed.connect(self._apply_sweep_cw)
        ctrl_layout.addRow("Center:", self._sw_center)
        ctrl_layout.addRow("Span:", self._sw_span)
        ctrl_layout.addRow("CW:", self._sw_cw)
        ctrl.setLayout(ctrl_layout)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Read current sweep state back from the device")
        refresh_btn.clicked.connect(lambda: self._refresh_sweep_status())

        self._sweep_status = QLabel("")
        self._sweep_status.setWordWrap(True)

        layout.addWidget(range_group)
        layout.addWidget(ctrl)
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

    # -- live graph panel --------------------------------------------------

    def _build_live_graph_panel(self):
        w = QWidget()
        outer = QHBoxLayout(w)

        # Left: trace controls
        ctrl = QWidget()
        ctrl.setMaximumWidth(300)
        ctrl_layout = QVBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)

        self._trace_on_btn: list[QPushButton] = []
        self._trace_calc_cb: list[QComboBox] = []
        self._trace_graph_chk: list[QCheckBox] = []
        self._trace_stats_btn: list[QPushButton] = []
        self._stats_trace_id: int | None = None
        self._trace_refresh_blocked = False

        trace_group = QGroupBox("Traces")
        trace_grid = QGridLayout(trace_group)
        trace_grid.setColumnStretch(1, 1)
        trace_grid.setHorizontalSpacing(8)

        # Column headers.
        for col, name in enumerate(["#", "Mode", "State", "Graph", "Stats"]):
            hdr = QLabel(name)
            hdr.setStyleSheet("font-weight: bold")
            hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            trace_grid.addWidget(hdr, 0, col)

        for i in range(3):
            tid = i + 1
            row = i + 1  # grid row, offset by header

            lbl = QLabel(str(tid))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            trace_grid.addWidget(lbl, row, 0)

            calc = QComboBox()
            calc.addItems(sorted(VALID_CALC))
            calc.setCurrentText("off")
            calc.setToolTip(f"Calc mode for trace {tid} — applied on selection")
            calc.currentTextChanged.connect(lambda val, t=tid: self._trace_set_calc(t, val))
            self._trace_calc_cb.append(calc)
            trace_grid.addWidget(calc, row, 1)

            on_btn = QPushButton("off")
            on_btn.setCheckable(True)
            on_btn.setToolTip(f"Toggle trace {tid} on/off")
            on_btn.toggled.connect(lambda checked, t=tid: self._trace_set_enabled(t, checked))
            self._trace_on_btn.append(on_btn)
            trace_grid.addWidget(on_btn, row, 2)

            graph_chk = QCheckBox()
            graph_chk.setToolTip(f"Add trace {tid} to the live graph")
            graph_chk.toggled.connect(lambda checked, t=tid: self._update_subscription())
            self._trace_graph_chk.append(graph_chk)
            hbox = QHBoxLayout()
            hbox.setContentsMargins(0, 0, 0, 0)
            hbox.addStretch()
            hbox.addWidget(graph_chk)
            hbox.addStretch()
            cw = QWidget()
            cw.setLayout(hbox)
            trace_grid.addWidget(cw, row, 3)

            stats_btn = QPushButton("off")
            stats_btn.setCheckable(True)
            stats_btn.setToolTip(f"Show auto-updating stats for trace {tid} (only one at a time)")
            stats_btn.toggled.connect(
                lambda checked, t=tid, b=None: self._on_stats_toggled(t, checked)
            )
            self._trace_stats_btn.append(stats_btn)
            trace_grid.addWidget(stats_btn, row, 4)

        ctrl_layout.addWidget(trace_group)

        self._trace_stats_display = QLabel("")
        self._trace_stats_display.setWordWrap(True)
        self._trace_stats_display.setMinimumHeight(120)
        self._trace_stats_display.setStyleSheet(
            "QLabel { font-family: monospace; font-size: 11px; }"
        )
        ctrl_layout.addWidget(self._trace_stats_display)
        ctrl_layout.addStretch()

        # Right: graph placeholder (filled in _connect)
        self._live_graph_container = QWidget()
        self._live_graph_container.setLayout(QVBoxLayout())
        self._live_graph_container.layout().setContentsMargins(0, 0, 0, 0)

        outer.addWidget(ctrl)
        outer.addWidget(self._live_graph_container, 1)
        return w

    def _update_subscription(self) -> None:
        """Start or stop the subscription based on active graph + stats traces."""
        graph = self._live_graph_widget if hasattr(self, "_live_graph_widget") else None
        if graph is None or self._rpc is None:
            return
        ids: set[int] = set()
        for i in range(3):
            if self._trace_graph_chk[i].isChecked():
                ids.add(i + 1)
        if self._stats_trace_id is not None:
            ids.add(self._stats_trace_id)
        if ids:
            calcs = {tid: self._trace_calc_cb[tid - 1].currentText() for tid in ids}
            graph.start(sorted(ids), calcs)
        else:
            graph.stop()

    def _refresh_trace_state(self) -> None:
        """Read current trace state from the device and update the UI."""
        if self._rpc is None:
            return
        try:
            raw = str(self._call("trace", "get_all"))
        except Exception:
            return
        import logging

        logging.getLogger("tsanet.gui").debug("trace.get_all response: %r", raw)
        self._trace_refresh_blocked = True
        try:
            for line in raw.strip().splitlines():
                logging.getLogger("tsanet.gui").debug("parse trace line: %r", line)
                parts = line.replace(",", " ").split()
                if len(parts) < 3:
                    continue
                try:
                    idx = int(parts[0])
                except ValueError:
                    continue
                on = parts[1] in ("1", "on", "ON")
                calc = parts[2]
                if 0 <= idx < 3:
                    self._trace_on_btn[idx].setChecked(on)
                    self._trace_on_btn[idx].setText("on" if on else "off")
                    if calc in VALID_CALC:
                        self._trace_calc_cb[idx].setCurrentText(calc)
        finally:
            self._trace_refresh_blocked = False

    # -- trace actions ------------------------------------------------------

    def _trace_set_enabled(self, tid: int, on: bool) -> None:
        if self._rpc is None or self._trace_refresh_blocked:
            return
        try:
            if on:
                self._call("trace", "enable", id=tid)
            else:
                self._call("trace", "disable", id=tid)
            self._trace_on_btn[tid - 1].setText("on" if on else "off")
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            # Revert the button state
            self._trace_refresh_blocked = True
            self._trace_on_btn[tid - 1].setChecked(not on)
            self._trace_on_btn[tid - 1].setText("on" if not on else "off")
            self._trace_refresh_blocked = False

    def _trace_set_calc(self, tid: int, calc: str) -> None:
        if self._rpc is None or not calc or self._trace_refresh_blocked:
            return
        try:
            self._call("trace", "enable_calc", id=tid, calc=calc)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _on_stats_toggled(self, tid: int, checked: bool) -> None:
        if self._trace_refresh_blocked:
            return
        if checked:
            # Turn off the previously active stats button.
            old_tid = self._stats_trace_id
            if old_tid is not None and old_tid != tid:
                self._trace_refresh_blocked = True
                self._trace_stats_btn[old_tid - 1].setChecked(False)
                self._trace_stats_btn[old_tid - 1].setText("off")
                self._trace_refresh_blocked = False
            self._stats_trace_id = tid
            self._update_subscription()
            self._trace_stats_btn[tid - 1].setText("on")
        else:
            if self._stats_trace_id == tid:
                self._stats_trace_id = None
                self._trace_stats_display.setText("")
                self._update_subscription()
            self._trace_stats_btn[tid - 1].setText("off")

    def _on_subscription_data(self, data: dict) -> None:
        """Handle subscription data for stats display."""
        tid = self._stats_trace_id
        if tid is None:
            return
        freqs = data.get("frequencies")
        traces = data.get("traces", {})
        vals = traces.get(str(tid))
        if not freqs or vals is None:
            return

        try:
            from tsanet.controller.stats import compute_stats

            result = compute_stats(freqs, vals, "dBm", freqs[0], freqs[-1])
        except Exception as exc:
            self._trace_stats_display.setText(f"Stats error: {exc}")
            return

        calc = self._trace_calc_cb[tid - 1].currentText()
        start_hz = freqs[0]
        stop_hz = freqs[-1]

        self._trace_stats_display.setText(
            f"Trace {tid}  Mode: {calc}  {_fmt(start_hz)} – {_fmt(stop_hz)}\n"
            f"  Channel power      : {result.channel_power:.1f} dBm\n"
            f"  Average            : {result.average:.1f} dBm\n"
            f"  Median             : {result.median:.1f} dBm\n"
            f"  Min                : {result.minimum:.1f} dBm  @ {_fmt(result.min_freq)}\n"
            f"  Max                : {result.maximum:.1f} dBm  @ {_fmt(result.max_freq)}\n"
            f"  Occupied BW (99%)  : {_fmt(result.occupied_bandwidth_hz)}\n"
            f"  PAPR               : {result.papr_db:.1f} dB\n"
            f"  Flatness           : {result.flatness_db:.1f} dB"
        )


def _fmt(hz: int) -> str:
    if hz >= 1_000_000_000:
        return f"{hz / 1e9:.3f} GHz"
    if hz >= 1_000_000:
        return f"{hz / 1e6:.3f} MHz"
    if hz >= 1_000:
        return f"{hz / 1e3:.3f} kHz"
    return f"{hz} Hz"
