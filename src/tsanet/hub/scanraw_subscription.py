"""Scanraw subscription — binary spectrum streaming.

The controller sends ``scanraw.subscribe`` to start a background loop that
streams binary scanraw frames from the selected device, decodes them to dBm
levels, and pushes them to the controller at the native sweep rate.

This replaces the per-trace text-polling subscription for higher resolution
and lower latency.
"""

from __future__ import annotations

import logging
import struct
import threading

from tsanet.common.errors import DispatchError, SessionError
from tsanet.device.transport import TinySA
from tsanet.hub.registry import DeviceRegistry
from tsanet.hub.session import SessionManager
from tsanet.protocol.messages import Event
from tsanet.protocol.transport import Connection

logger = logging.getLogger("tsanet.hub.subscriptions.scanraw")

#: Default reference level offset for dBm conversion on tinySA Ultra.
ULTRA_REF_LEVEL = 168.0


class ScanrawSubscriptionManager:
    """Owns the active scanraw subscription, at most one per session."""

    def __init__(self, registry: DeviceRegistry, sessions: SessionManager) -> None:
        self._registry = registry
        self._sessions = sessions
        self._lock = threading.Lock()
        self._active: ScanrawSubscription | None = None
        self._next_id = 0

    def subscribe(self, start_hz: int, stop_hz: int, pts: int, interval: float | None) -> dict:
        """Start a scanraw stream on the selected device."""
        with self._lock:
            self._stop_locked()

            session = self._sessions.current
            if session is None:
                raise SessionError("no active session")
            device_id = session.selected_device_id
            if device_id is None:
                raise DispatchError("no device selected")

            device = self._registry.get(device_id)
            sub_id = self._next_id
            self._next_id += 1

            sub = ScanrawSubscription(
                device.transport,
                session.connection,
                start_hz,
                stop_hz,
                pts,
                interval,
                sub_id,
            )
            sub.start()
            self._active = sub
            logger.info(
                "scanraw subscription #%d started: %d-%d Hz, %d pts",
                sub_id,
                start_hz,
                stop_hz,
                pts,
            )
            return {"subscription_id": sub_id, "active": True}

    def unsubscribe(self) -> dict:
        """Stop the active subscription."""
        with self._lock:
            if self._active is not None:
                logger.info("scanraw subscription #%d stopped", self._active._subscription_id)
            self._stop_locked()
            return {"active": False}

    def active(self) -> bool:
        with self._lock:
            return self._active is not None

    def shutdown(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        if self._active is not None:
            self._active.stop()
            self._active = None


class ScanrawSubscription:
    """Background thread streaming binary scanraw frames."""

    def __init__(
        self,
        tx: TinySA,
        connection: Connection,
        start_hz: int,
        stop_hz: int,
        pts: int,
        interval: float | None,
        subscription_id: int,
    ) -> None:
        self._tx = tx
        self._connection = connection
        self._start = start_hz
        self._stop = stop_hz
        self._pts = pts
        self._interval = interval
        self._subscription_id = subscription_id
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        try:
            tsa = self._tx._tsa
            if tsa is None:
                logger.error("scanraw: no tsapython backend available")
                return

            # Compute frequencies once — linear interpolation.
            freqs = [
                int(self._start + i * (self._stop - self._start) / max(self._pts - 1, 1))
                for i in range(self._pts)
            ]
            # Frequencies sent once at the start.
            self._push({"frequencies": freqs, "level": []})

            # Use continuous scan on device by driving scan_raw in a loop
            # with explicit sweep control, since continuous_scanraw is a
            # generator that calls the same underlying method.
            import time

            while not self._stop_event.is_set():
                cycle_start = time.monotonic()

                try:
                    raw = tsa.scan_raw(self._start, self._stop, self._pts)
                    # raw = b'{' + 3*pts bytes, skip '{'
                    data = raw[1:]
                    values = struct.unpack("<" + "xH" * self._pts, data)
                    dbm = [v / 32.0 - ULTRA_REF_LEVEL for v in values]
                    self._push({"frequencies": [], "level": dbm})
                except Exception:
                    # Skip a bad frame, try again next cycle.
                    pass

                if self._stop_event.is_set():
                    break
                if self._interval is not None:
                    elapsed = time.monotonic() - cycle_start
                    wait = self._interval - elapsed
                    if wait > 0:
                        self._stop_event.wait(wait)
        except Exception:
            pass

    def _push(self, data: dict) -> None:
        if self._stop_event.is_set():
            return
        event = Event(
            subscription_id=self._subscription_id,
            domain="scanraw",
            op="update",
            data=data,
        )
        self._connection.send(event)
