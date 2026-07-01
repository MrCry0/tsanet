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
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from pyqtgraph import ImageItem, GraphicsLayoutWidget
from pyqtgraph.colormap import get as get_colormap

from tsanet.controller.gui.stats_dialog import StatsDialog
from tsanet.controller.marker_lookup import nearest_amplitude
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

#: Label -> (TraceHold mode, window). Window only applies to "avg"; the
#: firmware has no arbitrary averaging count, only the aver4/aver16
#: presets (device/model.py::VALID_CALC), so those are the only two
#: average options offered here instead of a free-form count.
TRACE_MODE_LABELS = {
    "Live": ("live", 1),
    "Min hold": ("min", 1),
    "Max hold": ("max", 1),
    "Max decay": ("maxd", 1),
    "Average x4": ("avg", 4),
    "Average x16": ("avg", 16),
    "Quasi-peak": ("quasi", 1),
}

#: Shared margins/spacing so every settings section lines up the same way.
_SECTION_MARGINS = (6, 4, 6, 4)
_SECTION_SPACING = 6


def _style_layout(layout):
    """Apply the shared margins/spacing so every section's rows line up."""
    layout.setContentsMargins(*_SECTION_MARGINS)
    layout.setSpacing(_SECTION_SPACING)
    return layout


class _ScanrawEventBridge(QObject):
    """Marshals scanraw events from the RPC reader thread onto the GUI thread.

    RpcClient invokes the event callback directly on its background reader
    thread (see rpc_client.py::_reader_loop). Handling the event in place
    would touch Qt widgets from a non-GUI thread, and worse: any
    RpcClient.call() made from inside that handler (e.g. auto-unsubscribing
    after a single capture) can never complete, because the reader thread
    that would deliver its response is the very thread stuck waiting for
    it -- a guaranteed deadlock. Emitting a Qt signal from the reader
    thread and connecting it to a slot on the GUI thread uses Qt's default
    queued cross-thread delivery to defer the real handling to the GUI
    thread's event loop instead.
    """

    event_ready = Signal(object)


class _CollapsibleSection(QWidget):
    """A titled section with one toggle button to collapse/expand it."""

    def __init__(self, title: str, content: QWidget, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._toggle_btn = QToolButton()
        self._toggle_btn.setText(title)
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(True)
        self._toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle_btn.setArrowType(Qt.ArrowType.DownArrow)
        self._toggle_btn.setToolTip(f"Collapse/expand the {title} section")
        self._toggle_btn.setStyleSheet(
            "QToolButton { border: none; font-weight: bold; padding: 3px; }"
        )
        self._toggle_btn.toggled.connect(self._on_toggled)
        outer.addWidget(self._toggle_btn)

        self._content = content
        outer.addWidget(self._content)

    def _on_toggled(self, expanded: bool) -> None:
        self._content.setVisible(expanded)
        self._toggle_btn.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )


class SpectrumPanel(QWidget):
    """Combined sweep-control + live-spectrum + optional waterfall widget."""

    def __init__(self, rpc: RpcClient | None = None, parent=None):
        super().__init__(parent)
        self._rpc = rpc
        self._subscription_active = False
        self._single_shot = False
        self._freqs: list[int] = []
        self._last_level: list[float] = []
        self._waterfall_data: Optional[np.ndarray] = None
        self._waterfall_rows = WATERFALL_ROWS
        self._trace_holds: list[TraceHold | None] = [None] * len(TRACE_COLORS)
        #: Frequency in Hz for each of the 2 markers, or None if unplaced.
        self._marker_hz: list[Optional[int]] = [None, None]

        # See _ScanrawEventBridge's docstring: this defers scanraw event
        # handling from the RPC reader thread onto the GUI thread.
        self._event_bridge = _ScanrawEventBridge()
        self._event_bridge.event_ready.connect(self._on_scanraw_event)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # -- left panel: settings, in a vertical scroll area -----------------
        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        _style_layout(left_layout)

        left_layout.addWidget(self._build_sweep_group())
        left_layout.addWidget(self._build_signal_group())
        left_layout.addWidget(self._build_traces_group())
        left_layout.addWidget(self._build_markers_group())
        left_layout.addWidget(self._build_display_group())
        left_layout.addStretch()

        left_scroll = QScrollArea()
        left_scroll.setWidget(left_content)
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setMaximumWidth(300)

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

        layout.addWidget(left_scroll)
        layout.addLayout(right, 1)

        if rpc is not None:
            self._refresh_sweep_state()

    # -- sweep group --------------------------------------------------------

    def _build_sweep_group(self) -> QWidget:
        content = QWidget()
        form = _style_layout(QFormLayout(content))

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
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(_SECTION_SPACING)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply_sweep)
        btn_row.addWidget(apply_btn)
        form.addRow(btn_row)

        return _CollapsibleSection("Sweep", content)

    # -- signal group -------------------------------------------------------

    def _build_signal_group(self) -> QWidget:
        content = QWidget()
        layout = _style_layout(QFormLayout(content))

        self._lna_chk = QCheckBox("LNA (auto above 800 MHz)")
        self._lna_chk.setToolTip(
            "Force the low-noise amplifier on/off. The hub also enables it "
            "automatically for sweeps above 800 MHz regardless of this setting."
        )
        self._lna_chk.toggled.connect(self._set_lna)
        layout.addRow(self._lna_chk)

        spur_row = QHBoxLayout()
        spur_row.setContentsMargins(0, 0, 0, 0)
        spur_row.setSpacing(_SECTION_SPACING)
        self._spur_cb = QComboBox()
        self._spur_cb.addItems(["off", "on", "auto"])
        self._spur_cb.setCurrentText("off")
        self._spur_cb.currentTextChanged.connect(self._set_spur)
        spur_row.addWidget(QLabel("Spur:"))
        spur_row.addWidget(self._spur_cb)
        layout.addRow(spur_row)

        atten_row = QHBoxLayout()
        atten_row.setContentsMargins(0, 0, 0, 0)
        atten_row.setSpacing(_SECTION_SPACING)
        self._atten_cb = QComboBox()
        self._atten_cb.addItems(["auto"] + [str(v) for v in range(0, 31)])
        self._atten_cb.setToolTip("Input attenuation in dB (0-30), or automatic")
        self._atten_cb.currentTextChanged.connect(self._set_attenuation)
        atten_row.addWidget(QLabel("Attenuator:"))
        atten_row.addWidget(self._atten_cb)
        layout.addRow(atten_row)

        rbw_row = QHBoxLayout()
        rbw_row.setContentsMargins(0, 0, 0, 0)
        rbw_row.setSpacing(_SECTION_SPACING)
        self._rbw_auto_chk = QCheckBox("Auto")
        self._rbw_auto_chk.setChecked(True)
        self._rbw_auto_chk.toggled.connect(self._on_rbw_changed)
        self._rbw_spin = QSpinBox()
        self._rbw_spin.setRange(3, 600)
        self._rbw_spin.setValue(100)
        self._rbw_spin.setSuffix(" kHz")
        self._rbw_spin.setEnabled(False)
        self._rbw_spin.setToolTip("Resolution bandwidth in kHz (3-600)")
        self._rbw_spin.valueChanged.connect(self._on_rbw_changed)
        rbw_row.addWidget(QLabel("RBW:"))
        rbw_row.addWidget(self._rbw_auto_chk)
        rbw_row.addWidget(self._rbw_spin)
        layout.addRow(rbw_row)

        return _CollapsibleSection("Signal", content)

    def _set_spur(self, mode: str) -> None:
        if self._rpc is None:
            return
        if mode == "on":
            self._rpc.call("signal", "enable_spur")
        elif mode == "off":
            self._rpc.call("signal", "disable_spur")
        elif mode == "auto":
            self._rpc.call("signal", "enable_auto_spur")

    def _set_lna(self, on: bool) -> None:
        if self._rpc is None:
            return
        self._rpc.call("signal", "enable_lna" if on else "disable_lna")

    def _set_attenuation(self, value: str) -> None:
        if self._rpc is None:
            return
        self._rpc.call("signal", "set_attenuation", value=value if value == "auto" else int(value))

    def _on_rbw_changed(self, *_args) -> None:
        self._rbw_spin.setEnabled(not self._rbw_auto_chk.isChecked())
        if self._rpc is None:
            return
        value = "auto" if self._rbw_auto_chk.isChecked() else self._rbw_spin.value()
        self._rpc.call("sweep", "set_rbw", value=value)

    # -- traces group ---------------------------------------------------------

    def _build_traces_group(self) -> QWidget:
        content = QWidget()
        layout = _style_layout(QVBoxLayout(content))

        self._trace_enable_cb: list[QCheckBox] = []
        self._trace_mode_cb: list[QComboBox] = []
        for i, color in enumerate(TRACE_COLORS):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(_SECTION_SPACING)
            enable = QCheckBox()
            enable.setChecked(i == 0)
            enable.setStyleSheet(f"QCheckBox::indicator {{ background-color: {color}; }}")
            enable.setToolTip(f"Show trace {i + 1} on the plot")
            row.addWidget(enable)

            mode_cb = QComboBox()
            mode_cb.addItems(list(TRACE_MODE_LABELS))
            mode_cb.setToolTip(
                "Live: raw scan.  Min/Max hold: running extremum since last "
                "reset.  Max decay: max hold that falls back toward the "
                "live signal over time (approximate, not the device's own "
                "algorithm).  Average x4/x16: rolling mean, matching the "
                "device's aver4/aver16 presets -- the firmware has no "
                "arbitrary averaging count.  Quasi-peak: fast-rise, "
                "slow-fall approximation for relative comparison only, "
                "not a certified CISPR quasi-peak detector."
            )
            row.addWidget(QLabel(f"{i + 1}:"))
            row.addWidget(mode_cb)
            layout.addLayout(row)

            self._trace_enable_cb.append(enable)
            self._trace_mode_cb.append(mode_cb)

        reset_btn = QPushButton("Reset holds")
        reset_btn.setToolTip("Clear accumulated min/max/average state without stopping")
        reset_btn.clicked.connect(self._reset_holds)
        layout.addWidget(reset_btn)

        return _CollapsibleSection("Traces", content)

    def _reset_holds(self) -> None:
        for hold in self._trace_holds:
            if hold is not None:
                hold.reset()

    # -- markers group --------------------------------------------------------

    def _build_markers_group(self) -> QWidget:
        content = QWidget()
        layout = _style_layout(QVBoxLayout(content))

        self._marker_freq_edit: list[QLineEdit] = []
        self._marker_amp_label: list[QLabel] = []
        for i in range(2):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(_SECTION_SPACING)
            freq_edit = QLineEdit()
            freq_edit.setPlaceholderText("frequency")
            freq_edit.setToolTip(f"Marker {i + 1} frequency (e.g. 433.92mhz); blank to remove")
            freq_edit.editingFinished.connect(lambda i=i: self._apply_marker_freq(i))
            peak_btn = QPushButton("Peak")
            peak_btn.setToolTip(f"Move marker {i + 1} to the highest peak in the sweep")
            peak_btn.clicked.connect(lambda _checked=False, i=i: self._marker_to_peak(i))
            amp_label = QLabel("--")
            amp_label.setMinimumWidth(60)

            row.addWidget(QLabel(f"{i + 1}:"))
            row.addWidget(freq_edit)
            row.addWidget(peak_btn)
            row.addWidget(amp_label)
            layout.addLayout(row)

            self._marker_freq_edit.append(freq_edit)
            self._marker_amp_label.append(amp_label)

        self._marker_delta_label = QLabel("")
        self._marker_delta_label.setStyleSheet("color: #888")
        layout.addWidget(self._marker_delta_label)

        return _CollapsibleSection("Markers", content)

    def _apply_marker_freq(self, i: int) -> None:
        text = self._marker_freq_edit[i].text().strip()
        if not text:
            self._marker_hz[i] = None
            self._marker_amp_label[i].setText("--")
            if self._rpc is not None:
                self._rpc.call("marker", "disable", id=i + 1)
            return
        try:
            hz = parse_frequency(text)
        except ValueError:
            self._status.setText(f"Invalid marker frequency: {text!r}")
            return
        self._marker_hz[i] = hz
        if self._rpc is not None:
            self._rpc.call("marker", "enable", id=i + 1)
            self._rpc.call("marker", "set_freq", id=i + 1, hz=hz)

    def _marker_to_peak(self, i: int) -> None:
        if self._rpc is None:
            return
        self._rpc.call("marker", "enable", id=i + 1)
        self._rpc.call("marker", "move_to_peak", id=i + 1)
        try:
            raw = str(self._rpc.call("marker", "get", id=i + 1))
            hz = int(raw.split()[1])
        except (IndexError, ValueError):
            return
        self._marker_hz[i] = hz
        self._marker_freq_edit[i].setText(str(hz))

    def _update_marker_readouts(self) -> None:
        amplitudes: list[Optional[float]] = [None, None]
        for i, hz in enumerate(self._marker_hz):
            if hz is None:
                continue
            amp = nearest_amplitude(self._freqs, self._last_level, hz)
            amplitudes[i] = amp
            if amp is not None:
                self._marker_amp_label[i].setText(f"{amp:.1f} dBm")

        if amplitudes[0] is not None and amplitudes[1] is not None:
            d_hz = self._marker_hz[1] - self._marker_hz[0]
            d_amp = amplitudes[1] - amplitudes[0]
            self._marker_delta_label.setText(f"Δ: {_fmt_hz(d_hz)}, {d_amp:+.1f} dB")
        else:
            self._marker_delta_label.setText("")

    # -- display group ------------------------------------------------------

    def _build_display_group(self) -> QWidget:
        content = QWidget()
        layout = _style_layout(QFormLayout(content))

        self._wf_chk = QCheckBox("Waterfall")
        self._wf_chk.toggled.connect(self._toggle_waterfall)
        layout.addRow(self._wf_chk)

        self._cmap_cb = QComboBox()
        self._cmap_cb.addItems(["viridis", "inferno", "plasma", "grayscale", "hot"])
        self._cmap_cb.currentTextChanged.connect(self._set_colormap)
        layout.addRow("Colormap:", self._cmap_cb)

        self._wf_depth_spin = QSpinBox()
        self._wf_depth_spin.setRange(20, 2000)
        self._wf_depth_spin.setValue(WATERFALL_ROWS)
        self._wf_depth_spin.setSuffix(" sweeps")
        self._wf_depth_spin.setToolTip("Number of past sweeps kept in the waterfall")
        self._wf_depth_spin.valueChanged.connect(self._set_waterfall_depth)
        layout.addRow("WF depth:", self._wf_depth_spin)

        self._autorange_chk = QCheckBox("Auto-range Y")
        self._autorange_chk.setToolTip("Automatically scale the Y axis to the incoming data")
        self._autorange_chk.toggled.connect(self._set_autorange)
        layout.addRow(self._autorange_chk)

        ref_row = QHBoxLayout()
        ref_row.setContentsMargins(0, 0, 0, 0)
        ref_row.setSpacing(_SECTION_SPACING)
        self._ref_level_edit = QLineEdit()
        self._ref_level_edit.setPlaceholderText("auto")
        self._ref_level_edit.setToolTip("Reference level in dBm, or blank for automatic")
        self._ref_level_edit.editingFinished.connect(self._apply_ref_level)
        ref_row.addWidget(QLabel("Ref (dBm):"))
        ref_row.addWidget(self._ref_level_edit)
        layout.addRow(ref_row)

        scale_row = QHBoxLayout()
        scale_row.setContentsMargins(0, 0, 0, 0)
        scale_row.setSpacing(_SECTION_SPACING)
        self._scale_edit = QLineEdit()
        self._scale_edit.setPlaceholderText("auto")
        self._scale_edit.setToolTip("Scale in dB/division, or blank for automatic")
        self._scale_edit.editingFinished.connect(self._apply_scale)
        scale_row.addWidget(QLabel("Scale (dB/div):"))
        scale_row.addWidget(self._scale_edit)
        layout.addRow(scale_row)

        self._ref_spin = QSpinBox()
        self._ref_spin.setRange(25, 10000)
        self._ref_spin.setValue(150)
        self._ref_spin.setSuffix(" ms")
        self._ref_spin.setToolTip("Minimum interval between sweeps")
        layout.addRow("Interval:", self._ref_spin)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(_SECTION_SPACING)
        self._start_btn = QPushButton("Start")
        self._start_btn.setCheckable(True)
        self._start_btn.setToolTip("Start/stop continuous scanraw streaming")
        self._start_btn.toggled.connect(self._toggle_stream)
        btn_row.addWidget(self._start_btn)

        single_btn = QPushButton("Single")
        single_btn.setToolTip("Capture exactly one sweep, then stop")
        single_btn.clicked.connect(self._single_capture)
        btn_row.addWidget(single_btn)
        layout.addRow(btn_row)

        stats_btn = QPushButton("Stats...")
        stats_btn.setToolTip(
            "Open the trace statistics dialog (average, median, min/max, "
            "channel power, occupied bandwidth, PAPR, flatness, field strength)"
        )
        stats_btn.clicked.connect(self._show_stats)
        layout.addRow(stats_btn)

        return _CollapsibleSection("Display", content)

    def _show_stats(self) -> None:
        if self._rpc is None:
            self._status.setText("Connect to a hub first")
            return
        StatsDialog(self._rpc, self).exec()

    def _set_autorange(self, enabled: bool) -> None:
        if enabled:
            self._spec_plot.enableAutoRange("y", True)
        else:
            self._spec_plot.enableAutoRange("y", False)
            self._spec_plot.setYRange(DEFAULT_Y_MIN, DEFAULT_Y_MAX)

    def _apply_ref_level(self) -> None:
        if self._rpc is None:
            return
        text = self._ref_level_edit.text().strip()
        if not text:
            self._rpc.call("trace", "set_ref_level_auto")
        else:
            try:
                self._rpc.call("trace", "set_ref_level", dbm=float(text))
            except ValueError:
                self._status.setText(f"Invalid reference level: {text!r}")

    def _apply_scale(self) -> None:
        if self._rpc is None:
            return
        text = self._scale_edit.text().strip()
        try:
            value = "auto" if not text else float(text)
            self._rpc.call("trace", "set_scale", level=value)
        except ValueError:
            self._status.setText(f"Invalid scale: {text!r}")

    def _set_waterfall_depth(self, rows: int) -> None:
        self._waterfall_rows = rows
        self._waterfall_data = None

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

    def _single_capture(self) -> None:
        """Capture exactly one sweep, then unsubscribe.

        Implemented as a one-shot flag over the normal scanraw subscription
        rather than the device's own "trigger single" mode, since the hub
        drives its scan loop explicitly and does not rely on firmware-side
        triggering.
        """
        if self._start_btn.isChecked():
            return
        self._single_shot = True
        self._start_stream()

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

        # Set up one curve + hold per enabled trace slot (preserve waterfall).
        for _i, curve in self._curves:
            self._spec_plot.removeItem(curve)
        self._curves = []
        self._trace_holds = [None] * len(TRACE_COLORS)
        for i, color in enumerate(TRACE_COLORS):
            if not self._trace_enable_cb[i].isChecked():
                continue
            mode, window = TRACE_MODE_LABELS[self._trace_mode_cb[i].currentText()]
            self._trace_holds[i] = TraceHold(mode, window=window)
            curve = self._spec_plot.plot([], [], pen=color, name=f"Trace {i + 1}")
            self._curves.append((i, curve))
        self._waterfall_data = None

        # Subscribe to scanraw. Events arrive on the RPC reader thread; route
        # them through the signal bridge so handling runs on the GUI thread
        # (see _ScanrawEventBridge's docstring for why this matters).
        self._rpc.on_event(self._event_bridge.event_ready.emit)
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
        if not self._single_shot:
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
        self._last_level = raw
        for i, curve in self._curves:
            hold = self._trace_holds[i]
            assert hold is not None
            curve.setData(self._freqs[:n], hold.update(raw))

        self._update_marker_readouts()

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

        if self._single_shot:
            self._single_shot = False
            self._stop_stream()
            self._status.setText("Single capture complete")

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


def _fmt_hz(hz: int) -> str:
    if hz >= 1_000_000_000:
        return f"{hz / 1e9:.3f} GHz"
    if hz >= 1_000_000:
        return f"{hz / 1e6:.3f} MHz"
    if hz >= 1_000:
        return f"{hz / 1e3:.3f} kHz"
    return f"{hz} Hz"
