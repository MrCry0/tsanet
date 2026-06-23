"""Hub server: accept network connections and service RPC requests (brief 2, 11.5).

Wires together the device registry, session manager, dispatcher, and
subscription manager into a run loop. Supports both listen and dial network
modes, with per-connection threads in listen mode.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from tsanet.common.errors import ConnectionClosed, SessionBusy
from tsanet.device.discovery import list_serial_ports, open_serial_port
from tsanet.hub.config import HubConfig
from tsanet.hub.dispatcher import Dispatcher
from tsanet.hub.registry import DeviceRegistry, RegistryPoller
from tsanet.hub.session import SessionManager
from tsanet.hub.subscriptions import SubscriptionManager
from tsanet.protocol.messages import Request, Response, Status
from tsanet.protocol.security import NullSecurity
from tsanet.protocol.transport import Connection, Listener, dial, listen

logger = logging.getLogger("tsanet.hub")


class HubServer:
    """Owns the registry, session, dispatcher and subscription lifecycle.

    ``start()`` blocks until ``stop()`` is called (typically from a signal
    handler in the CLI layer).
    """

    def __init__(self, config: HubConfig) -> None:
        self._config = config
        self._registry = DeviceRegistry(list_serial_ports, open_serial_port)
        self._poller = RegistryPoller(self._registry, config.poll_interval)
        self._sessions = SessionManager()
        self._subscriptions = SubscriptionManager(self._registry, self._sessions)
        self._dispatcher = Dispatcher(self._registry, self._sessions, self._subscriptions)
        self._listener: Listener | None = None
        self._running = False
        self._active_connections: set[Connection] = set()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Run the hub. Blocks the calling thread.

        Call :meth:`stop` from a signal handler to initiate shutdown.
        """
        logger.info("starting hub: mode=%s transport=%s", self._config.network.mode, self._config.network.transport)
        self._poller.start()
        logger.info("device poller started (interval=%.1fs)", self._config.poll_interval)

        endpoint = self._config.network.endpoint()
        security = NullSecurity()

        if self._config.network.mode == "listen":
            self._listener = listen(endpoint, security)
            logger.info("listening on %s", self._describe(endpoint))
            self._running = True
            self._accept_loop()
        else:
            self._running = True
            self._dial_loop(endpoint, security)

        logger.info("hub stopped")

    def stop(self) -> None:
        """Initiate shutdown. Safe to call from any thread."""
        if not self._running:
            return
        logger.info("shutting down")
        self._running = False
        if self._listener is not None:
            self._listener.close()
        self._poller.stop()
        self._subscriptions.shutdown()
        self._registry.close()

    # -- connection loops --------------------------------------------------

    def _accept_loop(self) -> None:
        assert self._listener is not None
        while self._running:
            try:
                connection = self._listener.accept()
                logger.info("accepted connection")
                threading.Thread(target=self._serve, args=(connection,), daemon=True).start()
            except OSError:
                if self._running:
                    logger.exception("accept error")
                break

    def _dial_loop(self, endpoint: Any, security: Any) -> None:
        while self._running:
            try:
                connection = dial(endpoint, security)
                logger.info("connected to %s", self._describe(endpoint))
                self._serve(connection)
            except OSError:
                if self._running:
                    logger.debug("dial failed, retrying")
                    time.sleep(1)
            else:
                if self._running:
                    logger.info("connection closed, reconnecting")
                    time.sleep(1)

    def _serve(self, connection: Connection) -> None:
        """Handle a single controller connection."""
        try:
            peer = str(connection._sock.getpeername())
            transport = self._config.network.transport
            self._sessions.admit(connection, peer=peer, transport=transport)
        except SessionBusy as exc:
            connection.send(Response(id=0, status=Status.ERROR, error=str(exc)))
            connection.close()
            return
        except OSError:
            connection.close()
            return

        try:
            self._request_loop(connection)
        except ConnectionClosed:
            logger.debug("controller disconnected")
        except Exception:
            logger.exception("unhandled error in request loop")
        finally:
            # Clear the session if this connection still owns it (it may
            # have been evicted by a force-takeover from another connection).
            current = self._sessions.current
            if current is not None and current.connection is connection:
                self._sessions.disconnect()
            connection.close()

    def _request_loop(self, connection: Connection) -> None:
        while self._running:
            msg = connection.recv()
            if isinstance(msg, Request):
                resp = self._dispatcher.dispatch(msg, connection)
                connection.send(resp)
            else:
                logger.debug("ignoring non-request message: %s", type(msg).__name__)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _describe(endpoint: Any) -> str:
        if endpoint.transport == "tcp":
            return f"{endpoint.address}:{endpoint.port}"
        return endpoint.address
