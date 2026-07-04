"""End-to-end smoke test: a real MainWindow against a real HubServer.

Everything else in the suite either fakes the RPC layer (GUI tests) or
drives the transport/dispatcher directly (hub tests). This is the one place
that wires a real HubServer, a real RpcClient, and real GUI panels together
over an actual loopback socket, to catch integration bugs the layered unit
tests can't see -- in particular the two regressions this guards against:
an idle connection being torn down, and an abrupt disconnect crashing the
request loop.

Requires PySide6 (the "gui" extra); skips cleanly otherwise. No physical
tinySA is needed or assumed -- these checks only exercise the parts of the
stack that work identically with zero devices attached.

Not run by default: spinning up real sockets, threads, and a real Qt
event loop is slower and more failure-prone than the rest of the suite.
Pass --run-integration to include it.

Deliberately a single test function creating one MainWindow against one
HubServer, not one test per assertion: repeatedly constructing and tearing
down MainWindow/HubServer pairs within the same process was observed to
segfault or hang intermittently (PySide6's C++ object lifetime and
HubServer's un-joined accept-loop thread both outlive a naive teardown).
Splitting this into per-assertion tests would multiply that risk instead
of just testing more things. One long-lived pair sequencing every check
mirrors how the real GUI actually runs -- connect once, act on it,
disconnect -- and was verified stable across dozens of runs.
"""

from __future__ import annotations

import threading

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402

from tsanet.common.config import NetworkConfig, SecurityConfig  # noqa: E402
from tsanet.controller.config import ControllerConfig  # noqa: E402
from tsanet.controller.gui.device_panel import DevicePanel  # noqa: E402
from tsanet.controller.gui.main_window import MainWindow  # noqa: E402
from tsanet.controller.gui.spectrum_panel import SpectrumPanel  # noqa: E402
from tsanet.hub.config import HubConfig  # noqa: E402
from tsanet.hub.server import HubServer  # noqa: E402
from tsanet.protocol.messages import Request, Status  # noqa: E402
from tsanet.protocol.transport import TCP, Endpoint, dial  # noqa: E402

pytestmark = pytest.mark.integration


class _ReadyServer(HubServer):
    """HubServer that signals when its listener is bound, and remembers its
    accept-loop thread so the test can join it on teardown -- HubServer.stop()
    itself only asks the loop to stop, it doesn't wait for it to exit."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ready = threading.Event()
        self.accept_thread: threading.Thread | None = None

    def _accept_loop(self):
        self.accept_thread = threading.current_thread()
        self._ready.set()
        super()._accept_loop()


def _wait_until_session_free(port: int, attempts: int = 25, delay: float = 0.2):
    """Poll the hub until it accepts a new session or *attempts* run out.

    The peer disconnecting and the hub's own cleanup (_serve()'s finally
    block, running on that connection's own server-side thread) are both
    asynchronous with respect to the caller, so there is no way to await
    "the hub is ready" other than polling -- a single immediate attempt
    would be racing that cleanup thread's scheduling, not testing anything
    real about tsanet.
    """
    resp = None
    for _ in range(attempts):
        second = dial(Endpoint(TCP, "127.0.0.1", port))
        try:
            second.send(Request(id=1, domain="session", op="status"))
            resp = second.recv()
            if resp.status == Status.OK:
                return resp
        finally:
            second.close()
        threading.Event().wait(delay)
    pytest.fail(f"hub never freed the session in time: {resp}")


def test_gui_against_real_hub_end_to_end(monkeypatch):
    monkeypatch.setattr("tsanet.controller.rpc_client._RECV_TIMEOUT", 0.2)

    _app = QApplication.instance() or QApplication([])

    hub_config = HubConfig(
        network=NetworkConfig(mode="listen", transport="tcp", address="127.0.0.1", port=0),
        security=SecurityConfig(),
        poll_interval=60.0,
    )
    hub = _ReadyServer(hub_config)
    hub_thread = threading.Thread(target=hub.start, daemon=True)
    hub_thread.start()
    if not hub._ready.wait(timeout=3.0):
        hub.stop()
        raise RuntimeError("hub did not start in time")

    window = None
    try:
        controller_config = ControllerConfig(
            network=NetworkConfig(
                mode="dial", transport="tcp", address="127.0.0.1", port=hub._listener.port
            ),
            security=SecurityConfig(),
        )

        print("== connect: MainWindow against a real hub ==")
        window = MainWindow(config=controller_config)
        assert window._rpc is not None
        assert window._rpc._error is None
        assert "Connected" in window._status.currentMessage()
        central = window.centralWidget()
        assert isinstance(central, QTabWidget)
        assert isinstance(window._device_panel, DevicePanel)
        assert isinstance(window._spectrum_panel, SpectrumPanel)

        print("== real RPC round trip: session status, devices list ==")
        assert window._rpc.call("session", "status")["active"] is True
        assert window._rpc.call("devices", "list") == []

        print("== idle past the (shortened) recv timeout: must not disconnect ==")
        threading.Event().wait(1.0)  # several 0.2s timeout cycles while idle
        assert window._rpc._error is None, (
            f"an idle gap incorrectly killed the connection: {window._rpc._error}"
        )
        assert window._rpc.call("session", "status")["active"] is True

        print("== sweep-time control reaches the real dispatcher ==")
        window._spectrum_panel._sweeptime_spin.setValue(1500)
        with pytest.raises(Exception, match="no device selected"):
            window._spectrum_panel._set_sweep_time()

        print("== abrupt disconnect: hub must recover, not crash ==")
        reader = window._rpc._reader
        window._rpc._connection._sock.close()
        reader.join(timeout=3.0)
        assert not reader.is_alive(), "reader thread did not notice the closed socket"
        window._rpc._connection = None  # already closed above
        _wait_until_session_free(hub._listener.port)

        print("== reconnect and clean disconnect: hub must recover again ==")
        window2 = MainWindow(config=controller_config)
        assert window2._rpc.call("session", "status")["active"] is True
        window2._rpc.close()
        _wait_until_session_free(hub._listener.port)

        print("ALL CHECKS PASSED")
    finally:
        if window is not None and window._rpc is not None:
            window._rpc.close()
        hub.stop()
        if hub.accept_thread is not None:
            hub.accept_thread.join(timeout=2.0)
        hub_thread.join(timeout=2.0)
