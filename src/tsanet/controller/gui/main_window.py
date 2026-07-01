"""Main window for the controller GUI."""

from __future__ import annotations

import logging
from logging import LogRecord

from PySide6.QtCore import Qt, QObject, Signal, Slot
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QStatusBar,
    QTabWidget,
    QWidget,
)

from tsanet import __version__
from tsanet.controller.config import DEFAULT_CONFIG_PATH
from tsanet.controller.gui.capture_viewer import CaptureViewer
from tsanet.controller.gui.connection_dialog import ConnectionDialog
from tsanet.controller.gui.device_panel import DevicePanel
from tsanet.controller.gui.spectrum_panel import SpectrumPanel
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
        self._spectrum_panel = QWidget()
        self._capture_viewer = QWidget()

        self._SPECTRUM_TAB = 1

        tabs.addTab(self._device_panel, "Devices")
        tabs.addTab(self._spectrum_panel, "Spectrum")
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

            self._spectrum_panel = SpectrumPanel(self._rpc)
            central.removeTab(1)
            central.insertTab(1, self._spectrum_panel, "Spectrum")

            self._capture_viewer = CaptureViewer(self._rpc)
            central.removeTab(2)
            central.insertTab(2, self._capture_viewer, "Capture")

            self._status.showMessage("Connected — use the Spectrum tab to configure sweeps")

    def _on_tab_changed(self, index):
        if self._SPECTRUM_TAB == index and self._rpc is not None:
            self._status.showMessage("Spectrum — set sweep range, start streaming")
        elif index == 0 and self._rpc is not None:
            self._status.showMessage("Devices tab — click a device to select it")
        elif index == 2 and self._rpc is not None:
            self._status.showMessage("Capture tab — fetch a screenshot from the device")
