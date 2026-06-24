"""End-to-end tests that require a real tinySA device attached.

These tests start a local hub and run a controller against it.  They are
skipped by default; pass ``--run-hardware`` to enable them::

    pytest tests/test_hardware.py --run-hardware

By default the first available serial port is used.  Override with::

    TINYSA_PORT=/dev/ttyACM1 pytest tests/test_hardware.py --run-hardware
"""

from __future__ import annotations

import threading
import time

import pytest

from tsanet.common.config import NetworkConfig, SecurityConfig
from tsanet.controller.config import ControllerConfig
from tsanet.controller.rpc_client import RpcClient
from tsanet.hub.config import HubConfig
from tsanet.hub.server import HubServer

# ----------------------------------------------------------------------


def _hub_config(port):
    return HubConfig(
        network=NetworkConfig(mode="listen", transport="tcp", address="127.0.0.1", port=port),
        security=SecurityConfig(),
        poll_interval=30.0,
    )


def _ctl_config(port):
    return ControllerConfig(
        network=NetworkConfig(mode="dial", transport="tcp", address="127.0.0.1", port=port),
        security=SecurityConfig(),
    )


class _ReadyHub(HubServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ready = threading.Event()

    def _accept_loop(self):
        self._ready.set()
        super()._accept_loop()


class _Harness:
    def __init__(self):
        self.hub_cfg = _hub_config(0)
        self.hub = _ReadyHub(self.hub_cfg)
        self._t = threading.Thread(target=self.hub.start, daemon=True)
        self._t.start()
        if not self.hub._ready.wait(timeout=5.0):
            self.hub.stop()
            raise RuntimeError("hub did not start")
        self.port = self.hub._listener.port

    def client(self):
        c = RpcClient(_ctl_config(self.port))
        c.connect()
        return c

    def stop(self):
        self.hub.stop()
        self._t.join(timeout=3.0)


# ----------------------------------------------------------------------


@pytest.mark.hardware
class TestHardware:
    def test_device_version(self):
        h = _Harness()
        try:
            c = h.client()
            ver = c.call("device", "get_version")
            assert "tinySA" in str(ver)
            c.close()
        finally:
            h.stop()

    def test_devices_list(self):
        h = _Harness()
        try:
            c = h.client()
            devices = c.call("devices", "list")
            assert len(devices) >= 1
            assert devices[0]["model"] in ("tinySA", "tinySA4")
            c.close()
        finally:
            h.stop()

    def test_sweep_get_and_set_range(self):
        h = _Harness()
        try:
            c = h.client()
            raw = str(c.call("sweep", "get"))
            parts = raw.split()
            assert len(parts) >= 2

            # Set a known range.
            c.call("sweep", "set_start_stop", start=100_000_000, stop=500_000_000, points=101)
            time.sleep(0.2)
            raw2 = str(c.call("sweep", "get"))
            parts2 = raw2.split()
            assert int(parts2[0]) == 100_000_000
            assert int(parts2[1]) == 500_000_000

            c.close()
        finally:
            h.stop()

    def test_sweep_high_frequency_auto_lna(self):
        """Setting a center > 800 MHz should auto-enable LNA."""
        h = _Harness()
        try:
            c = h.client()

            # Set center above low-band threshold.
            c.call("sweep", "set_center", hz=900_000_000)
            time.sleep(0.1)

            raw = str(c.call("sweep", "get"))
            parts = raw.split()
            center = (int(parts[0]) + int(parts[1])) // 2
            # The center should not be clamped to 800 MHz.
            assert center > 800_000_000, f"center clamped to {center} Hz"

            c.close()
        finally:
            h.stop()

    def test_capture_fetch(self):
        h = _Harness()
        try:
            c = h.client()
            png = c.call("capture", "fetch")
            assert isinstance(png, bytes)
            assert png[:8] == b"\x89PNG\r\n\x1a\n"
            c.close()
        finally:
            h.stop()

    def test_trace_fetch_data(self):
        h = _Harness()
        try:
            c = h.client()
            c.call("trace", "enable", id=1)
            data = c.call("trace", "fetch_data", ids=[1])
            assert "frequencies" in data
            assert "1" in data["traces"]
            assert len(data["frequencies"]) == len(data["traces"]["1"])
            c.close()
        finally:
            h.stop()

    def test_session_list(self):
        h = _Harness()
        try:
            c = h.client()
            sessions = c.call("session", "list")
            assert isinstance(sessions, list)
            assert len(sessions) >= 1
            c.close()
        finally:
            h.stop()
