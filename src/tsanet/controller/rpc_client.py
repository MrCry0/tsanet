"""RPC client for communicating with a tsanet hub (brief 2, 9, 11.6).

Manages the network connection lifecycle (dial or listen) and wraps
request/response exchanges into a simple call API.  When a subscription
is active the hub pushes ``Event`` messages on the same connection;
callers can register a callback via ``on_event()`` to receive them.
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
    """Connect to a hub and send RPC requests."""

    def __init__(self, config: ControllerConfig) -> None:
        self._config = config
        self._connection: Connection | None = None
        self._listener: Listener | None = None
        self._lock = threading.Lock()
        self._next_id = 0
        self._event_cb: EventCallback | None = None

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> None:
        """Establish the network connection (dial or listen)."""
        endpoint = self._config.network.endpoint()
        security = NullSecurity()

        if self._config.network.mode == "listen":
            self._listener = listen(endpoint, security)
            self._connection = self._listener.accept()
        else:
            self._connection = dial(endpoint, security)

    def close(self) -> None:
        """Close the connection and stop listening if applicable."""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            if self._listener is not None:
                self._listener.close()
                self._listener = None

    # -- events ------------------------------------------------------------

    def on_event(self, cb: EventCallback) -> None:
        """Register a callback for unsolicited ``Event`` messages."""
        self._event_cb = cb

    # -- RPC ---------------------------------------------------------------

    def call(self, domain: str, op: str, **args: object) -> object:
        """Send a request and return the response data.

        Raises :class:`RpcError` if the hub returns an error.
        """
        with self._lock:
            conn = self._connection
            if conn is None:
                raise TransportError("not connected")
            req_id = self._next_id
            self._next_id += 1
            conn.send(Request(id=req_id, domain=domain, op=op, args=args))
            while True:
                msg = conn.recv()
                if isinstance(msg, Response):
                    if msg.id != req_id:
                        continue
                    if msg.status == Status.ERROR:
                        raise RpcError(msg.error or "unknown error")
                    return msg.data
                if isinstance(msg, Event):
                    if self._event_cb is not None:
                        self._event_cb(msg)
                    continue
                raise TransportError(f"unexpected message type: {type(msg).__name__}")
