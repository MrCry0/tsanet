"""Live-graph subscription push loop (brief 6.3, 11.5).

The controller sends ``trace.subscribe`` to start a background loop that
periodically pulls frequency and trace-value data from the selected device
and pushes ``event`` messages back to the controller. ``trace.unsubscribe``
stops the loop.

Frequencies are cached; they are only re-sent in event payloads when they
differ from the previously sent set (e.g. the sweep range changed).
"""

from __future__ import annotations

import logging
import threading
import time

from tsanet.common.errors import DispatchError, SessionError
from tsanet.device.commands import trace as cmd_trace
from tsanet.device.parsing import parse_frequencies, parse_trace_values
from tsanet.device.transport import TinySA
from tsanet.hub.registry import DeviceRegistry
from tsanet.hub.session import SessionManager
from tsanet.protocol.messages import Event
from tsanet.protocol.transport import Connection

logger = logging.getLogger("tsanet.hub.subscriptions")


class SubscriptionManager:
    """Owns the active live-graph subscription, at most one per session."""

    def __init__(self, registry: DeviceRegistry, sessions: SessionManager) -> None:
        self._registry = registry
        self._sessions = sessions
        self._lock = threading.Lock()
        self._active: Subscription | None = None
        self._next_id = 0

    # -- public API --------------------------------------------------------

    def subscribe(self, ids: list[int], interval: float | None) -> dict:
        """Start a push loop for *ids* on the selected device.

        *interval* is seconds between pushes; ``None`` means max speed
        (no artificial delay).  Any previous subscription is stopped first.
        """
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

            sub = Subscription(device.transport, session.connection, ids, interval, sub_id)
            sub.start()
            self._active = sub
            logger.info("subscription #%d started: ids=%s interval=%s", sub_id, ids, interval)
            return {"subscription_id": sub_id, "active": True}

    def unsubscribe(self) -> dict:
        """Stop the active subscription, if any."""
        with self._lock:
            if self._active is not None:
                logger.info("subscription #%d stopped", self._active._subscription_id)
            self._stop_locked()
            return {"active": False}

    def active(self) -> bool:
        with self._lock:
            return self._active is not None

    def shutdown(self) -> None:
        """Stop the active subscription (called on hub shutdown)."""
        with self._lock:
            self._stop_locked()

    # -- internals ---------------------------------------------------------

    def _stop_locked(self) -> None:
        if self._active is not None:
            self._active.stop()
            self._active = None


class Subscription:
    """Background thread that polls trace data and pushes events."""

    def __init__(
        self,
        tx: TinySA,
        connection: Connection,
        ids: list[int],
        interval: float | None,
        subscription_id: int,
    ) -> None:
        self._tx = tx
        self._connection = connection
        self._ids = ids
        self._interval = interval
        self._subscription_id = subscription_id
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # -- loop --------------------------------------------------------------

    def _run(self) -> None:
        try:
            # Fetch initial frequencies and push them immediately so the
            # controller has a frequency axis before the first trace values.
            last_freqs = self._fetch_frequencies()
            if last_freqs is not None:
                self._push({"frequencies": last_freqs, "traces": {}})

            while not self._stop_event.is_set():
                cycle_start = time.monotonic()

                # Fetch trace values for each requested id.
                traces: dict[str, list[float]] = {}
                for tid in self._ids:
                    try:
                        traces[str(tid)] = parse_trace_values(cmd_trace.fetch_value(self._tx, tid))
                    except Exception:
                        # A single bad trace read shouldn't kill the loop;
                        # skip this cycle and try again next time.
                        break
                else:
                    # Only push if all traces were read successfully.
                    freqs = self._fetch_frequencies()
                    data: dict = {"traces": traces}
                    if freqs is not None and freqs != last_freqs:
                        data["frequencies"] = freqs
                        last_freqs = freqs
                    self._push(data)

                # Pace the loop.
                if self._interval is not None:
                    elapsed = time.monotonic() - cycle_start
                    wait = self._interval - elapsed
                    if wait > 0:
                        self._stop_event.wait(wait)
        except Exception:
            # Connection died, device disappeared, or serial link broke.
            # The subscription ends gracefully.
            pass

    # -- helpers -----------------------------------------------------------

    def _fetch_frequencies(self) -> list[int] | None:
        try:
            return parse_frequencies(cmd_trace.get_frequencies(self._tx))
        except Exception:
            return None

    def _push(self, data: dict) -> None:
        if self._stop_event.is_set():
            return
        event = Event(
            subscription_id=self._subscription_id,
            domain="trace",
            op="update",
            data=data,
        )
        self._connection.send(event)
