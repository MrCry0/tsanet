"""RPC client for communicating with a tsanet hub (brief 2, 9, 11.6).

A background reader thread continuously reads messages from the connection.
Responses are matched to pending ``call()`` invocations via a condition
variable; ``Event`` messages are dispatched to the registered callback.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from tsanet.common.errors import TransportError
from tsanet.controller.config import ControllerConfig
from tsanet.protocol.messages import Event, Request, Response, Status
from tsanet.protocol.security import NullSecurity
from tsanet.protocol.transport import Connection, Listener, dial, listen


class RpcError(TransportError):
    """The hub returned an error response for the RPC call."""


EventCallback = Callable[[Event], None]


class RpcClient:
    """Connect to a hub and send RPC requests.

    Unsolicited ``Event`` messages (e.g. live-graph subscription updates)
    are delivered to the callback registered via ``on_event()``.
    """

    def __init__(self, config: ControllerConfig) -> None:
        self._config = config
        self._connection: Connection | None = None
        self._listener: Listener | None = None
        self._lock = threading.Lock()
        self._next_id = 0
        self._event_cb: EventCallback | None = None

        # Matching of responses to call() invocations.
        self._pending: dict[int, object] = {}  # request_id -> response data or exception
        self._pending_cond = threading.Condition()

        self._reader: threading.Thread | None = None
        self._running = False

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> None:
        """Establish the network connection and start the reader thread."""
        endpoint = self._config.network.endpoint()
        security = NullSecurity()

        if self._config.network.mode == "listen":
            self._listener = listen(endpoint, security)
            self._connection = self._listener.accept()
        else:
            self._connection = dial(endpoint, security)

        self._running = True
        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader.start()

    def close(self) -> None:
        """Stop the reader thread and close the connection."""
        self._running = False
        # Wake pending call()s so they don't hang.
        with self._pending_cond:
            self._pending_cond.notify_all()
        if self._reader is not None:
            self._reader.join(timeout=2.0)
            self._reader = None
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            if self._listener is not None:
                self._listener.close()
                self._listener = None

    # -- events ------------------------------------------------------------

    def on_event(self, cb: EventCallback | None) -> None:
        """Register or clear the callback for unsolicited ``Event`` messages."""
        self._event_cb = cb

    # -- RPC ---------------------------------------------------------------

    def call(self, domain: str, op: str, **args: object) -> object:
        """Send a request and block until the matching response arrives.

        Unsolicited events received while waiting are dispatched to the
        event callback.

        Raises :class:`RpcError` if the hub returns an error.
        """
        with self._lock:
            conn = self._connection
            if conn is None:
                raise TransportError("not connected")
            req_id = self._next_id
            self._next_id += 1
            conn.send(Request(id=req_id, domain=domain, op=op, args=args))

        with self._pending_cond:
            while req_id not in self._pending:
                self._pending_cond.wait()
            result = self._pending.pop(req_id)

        if isinstance(result, Exception):
            raise result
        return result

    # -- reader ------------------------------------------------------------

    def _reader_loop(self) -> None:
        while self._running:
            try:
                msg = self._connection.recv()  # type: ignore[union-attr]
            except Exception as exc:
                if self._running:
                    self._dispatch_error(exc)
                break

            if isinstance(msg, Response):
                self._dispatch_response(msg)
            elif isinstance(msg, Event):
                cb = self._event_cb
                if cb is not None:
                    try:
                        cb(msg)
                    except Exception:
                        pass

    def _dispatch_response(self, resp: Response) -> None:
        with self._pending_cond:
            if resp.status == Status.ERROR:
                self._pending[resp.id] = RpcError(resp.error or "unknown error")
            else:
                self._pending[resp.id] = resp.data
            self._pending_cond.notify_all()

    def _dispatch_error(self, exc: Exception) -> None:
        with self._pending_cond:
            for rid in list(self._pending):
                self._pending[rid] = exc
            self._pending_cond.notify_all()
