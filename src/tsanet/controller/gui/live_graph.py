"""Live signal graph panel with subscription push."""

from __future__ import annotations

from collections.abc import Callable

import pyqtgraph as pg
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
)

from tsanet.controller.rpc_client import RpcClient
from tsanet.protocol.messages import Event


class _EventBridge(QObject):
    """Receives events from the reader thread and forwards to the GUI thread."""

    arrived = Signal(dict)


DataCallback = Callable[[dict], None]


class LiveGraphPanel(QWidget):
    """Pyqtgraph plot that displays live trace data from a subscription.

    Call :meth:`start` with the list of trace IDs and their calc modes.
    Call :meth:`stop` to end the subscription.  Use :meth:`graph` to
    embed the PlotWidget into an external layout.

    Register a :meth:`set_data_callback` to receive every subscription
    update payload for sharing with other consumers (e.g. stats).
    """

    def __init__(self, rpc: RpcClient, parent=None):
        super().__init__(parent)
        self._rpc = rpc
        self._running = False
        self._frequencies: list[int] = []
        self._data_cb: DataCallback | None = None

        self._bridge = _EventBridge()
        self._bridge.arrived.connect(self._on_event)

        self._plot = pg.PlotWidget()
        self._plot.setLabel("bottom", "Frequency", "Hz")
        self._plot.setLabel("left", "Amplitude", "dBm")
        self._plot.showGrid(x=True, y=True)

        self._curves: list = [None, None, None]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

    @property
    def graph(self):
        """The PlotWidget, for embedding in an external layout."""
        return self._plot

    def set_data_callback(self, cb: DataCallback | None) -> None:
        """Register or clear a callback receiving every subscription payload."""
        self._data_cb = cb

    def start(
        self,
        ids: list[int],
        calcs: dict[int, str],
        *,
        graph_ids: list[int] | None = None,
        interval_ms: int = 250,
    ) -> None:
        """Begin live graphing for *ids* with the given calc modes.

        *ids* is the set of traces to subscribe to (graph + stats union).
        *graph_ids* is the subset that should appear as curves on the plot.
        *interval_ms* is the subscription push interval in milliseconds.
        """
        if graph_ids is None:
            graph_ids = ids
        if self._running:
            self.stop()

        for tid in ids:
            calc = calcs.get(tid, "minh")
            try:
                self._rpc.call("trace", "enable", id=tid)
                if calc != "off":
                    self._rpc.call("trace", "enable_calc", id=tid, calc=calc)
            except Exception:
                pass

        self._plot.clear()
        colors = [(255, 100, 100), (100, 255, 100), (100, 100, 255)]
        graph_set = set(graph_ids)
        for i in range(3):
            tid = i + 1
            if tid in graph_set:
                curve = self._plot.plot([], [], pen=pg.mkPen(color=colors[i], width=1.5))
                self._curves[i] = curve
            else:
                self._curves[i] = None

        interval_sec = interval_ms / 1000.0 if interval_ms > 0 else None
        self._running = True
        self._rpc.on_event(self._on_reader_event)
        self._rpc.call("trace", "subscribe", ids=ids, interval=interval_sec)

    def stop(self) -> None:
        """End the subscription and clear the graph."""
        self._running = False
        self._rpc.on_event(None)
        try:
            self._rpc.call("trace", "unsubscribe")
        except Exception:
            pass
        self._plot.clear()
        for i in range(3):
            self._curves[i] = None

    def _on_reader_event(self, event: Event):
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
                    vals = traces[tid]
                    n = min(len(self._frequencies), len(vals))
                    curve.setData(self._frequencies[:n], vals[:n])

        cb = self._data_cb
        if cb is not None:
            cb(data)
