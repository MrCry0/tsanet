"""RPC client for communicating with a tsanet hub (brief 2, 9, 11.6).

Manages the network connection lifecycle (dial or listen) and wraps
request/response exchanges into a simple call API.
"""

from __future__ import annotations

import threading

from tsanet.common.errors import TransportError
from tsanet.controller.config import ControllerConfig
from tsanet.protocol.messages import Request, Response, Status
from tsanet.protocol.security import NullSecurity
from tsanet.protocol.transport import Connection, Listener, dial, listen


class RpcError(TransportError):
    """The hub returned an error response for the RPC call."""


class RpcClient:
    """Connect to a hub and send RPC requests."""

    def __init__(self, config: ControllerConfig) -> None:
        self._config = config
        self._connection: Connection | None = None
        self._listener: Listener | None = None
        self._lock = threading.Lock()
        self._next_id = 0

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
            resp = conn.recv()
            if not isinstance(resp, Response):
                raise TransportError(f"unexpected message type: {type(resp).__name__}")
            if resp.status == Status.ERROR:
                raise RpcError(resp.error or "unknown error")
            return resp.data
