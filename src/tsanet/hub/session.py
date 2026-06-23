"""Single global controller session with force-takeover (brief 2.3).

The hub admits one controller session at a time. A second admission is
rejected with :class:`SessionBusy` unless takeover is requested, which evicts
the incumbent. The selected device scopes a session's device-directed
commands (brief 2.4).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from tsanet.common.errors import SessionBusy
from tsanet.protocol.transport import Connection


@dataclass
class Session:
    connection: Connection
    peer: str = ""
    selected_device_id: str | None = None
    started_at: float = field(default_factory=time.time)


class SessionManager:
    """Tracks the single active controller session."""

    def __init__(self) -> None:
        self._current: Session | None = None
        self._lock = threading.Lock()
        self._allow_takeover = False

    def admit(self, connection: Connection, *, peer: str = "", force: bool = False) -> Session:
        """Admit a controller, evicting the incumbent if ``force`` is set.

        Raises :class:`SessionBusy` if a session is active and ``force`` is not
        and takeover has not been allowed via :meth:`allow_takeover`.
        """
        with self._lock:
            if self._current is not None:
                if not force and not self._allow_takeover:
                    raise SessionBusy("a controller session is already active")
                self._evict_locked()
                self._allow_takeover = False
            session = Session(connection=connection, peer=peer)
            self._current = session
            return session

    def disconnect(self) -> None:
        """End the active session, if any, without closing the connection.

        The caller (hub server) is responsible for closing the connection
        after the disconnect response has been sent.
        """
        with self._lock:
            self._evict_locked(close=False)

    def select_device(self, device_id: str) -> None:
        """Scope the active session's device commands to ``device_id``."""
        with self._lock:
            if self._current is None:
                raise SessionBusy("no active session")
            self._current.selected_device_id = device_id

    @property
    def current(self) -> Session | None:
        with self._lock:
            return self._current

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self._current is None:
                return {"active": False}
            return {
                "active": True,
                "peer": self._current.peer,
                "selected_device": self._current.selected_device_id,
                "uptime_seconds": round(time.time() - self._current.started_at, 3),
            }

    def allow_takeover(self) -> None:
        """Allow the next admission to evict the current session.

        Called by the ``session.force_takeover`` RPC so a controller can
        enable a different client to take over.
        """
        with self._lock:
            self._allow_takeover = True

    def _evict_locked(self, *, close: bool = True) -> None:
        if self._current is not None:
            if close:
                self._current.connection.close()
            self._current = None
