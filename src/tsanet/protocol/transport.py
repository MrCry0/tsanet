"""Connection establishment and framed message transport (brief 2.1-2.2, 3.1).

Either side can listen or dial, over TCP or a Unix domain socket; the role
that establishes the connection is independent of the symmetric message
protocol that runs over it. A :class:`Connection` carries framed messages in
both directions regardless of which side called :func:`listen` or :func:`dial`.
"""

from __future__ import annotations

import contextlib
import os
import socket
import threading
from dataclasses import dataclass

from tsanet.common.errors import ConnectionClosed
from tsanet.protocol.codec import HEADER_SIZE, decode_length, decode_payload, encode
from tsanet.protocol.messages import Message
from tsanet.protocol.security import NullSecurity, SecurityProvider

TCP = "tcp"
UNIX = "unix"


@dataclass(frozen=True)
class Endpoint:
    """Where to bind or connect.

    For ``tcp`` the address is a host and ``port`` is required; for ``unix``
    the address is a socket path and the port is ignored.
    """

    transport: str
    address: str
    port: int | None = None

    def __post_init__(self) -> None:
        if self.transport not in (TCP, UNIX):
            raise ValueError(f"unknown transport: {self.transport!r}")
        if self.transport == TCP and self.port is None:
            raise ValueError("tcp endpoint requires a port")


class Connection:
    """A framed message channel over a connected socket."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._send_lock = threading.Lock()

    def send(self, message: Message) -> None:
        frame = encode(message)
        try:
            with self._send_lock:
                self._sock.sendall(frame)
        except TimeoutError:
            # A timeout means the OS-level send timed out, not that the
            # peer is gone -- callers (e.g. RpcClient) may have their own
            # retry/backoff handling for it. Let it propagate unchanged;
            # only fold real disconnect signals into ConnectionClosed below.
            raise
        except OSError as exc:
            # A dead peer surfaces here as BrokenPipeError/ConnectionResetError
            # (an abrupt disconnect, e.g. the process was killed or the
            # network dropped) rather than a clean EOF. Normalize it to the
            # same signal recv() uses so callers only need to handle one
            # "the peer is gone" exception, not track every OSError subtype
            # the OS might raise for a dead socket.
            raise ConnectionClosed(f"connection lost while sending: {exc}") from exc

    def recv(self) -> Message:
        length = decode_length(self._recv_exact(HEADER_SIZE))
        return decode_payload(self._recv_exact(length))

    def _recv_exact(self, count: int) -> bytes:
        chunks: list[bytes] = []
        remaining = count
        while remaining > 0:
            try:
                chunk = self._sock.recv(remaining)
            except TimeoutError:
                # A read timeout (e.g. RpcClient's 3s sock.settimeout(), used
                # to periodically wake the reader loop) is not a disconnect
                # signal -- it just means no data arrived in time. Callers
                # that set a timeout already have their own retry handling
                # for it (see RpcClient._reader_loop's "except socket.timeout:
                # continue"); converting it to ConnectionClosed here would
                # tear down a perfectly healthy, merely idle connection.
                raise
            except OSError as exc:
                # Same normalization as send(): an abrupt disconnect (TCP
                # RST) raises ConnectionResetError/OSError directly instead
                # of recv() returning b"" the way a clean FIN does.
                raise ConnectionClosed(f"connection lost: {exc}") from exc
            if not chunk:
                raise ConnectionClosed("peer closed the connection")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._sock.close()

    def __enter__(self) -> Connection:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class Listener:
    """A bound, listening socket that accepts :class:`Connection` peers."""

    def __init__(self, sock: socket.socket, endpoint: Endpoint, security: SecurityProvider) -> None:
        self._sock = sock
        self._endpoint = endpoint
        self._security = security

    def accept(self) -> Connection:
        raw, _ = self._sock.accept()
        return Connection(self._security.wrap(raw, server=True))

    @property
    def port(self) -> int:
        """The bound TCP port (useful when binding to port 0)."""
        return self._sock.getsockname()[1]

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._sock.close()
        if self._endpoint.transport == UNIX:
            with contextlib.suppress(OSError):
                os.unlink(self._endpoint.address)

    def __enter__(self) -> Listener:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def listen(
    endpoint: Endpoint, security: SecurityProvider | None = None, *, backlog: int = 1
) -> Listener:
    """Bind and listen, returning a :class:`Listener`."""
    security = security or NullSecurity()
    sock = _new_socket(endpoint)
    try:
        if endpoint.transport == TCP:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((endpoint.address, endpoint.port))
        else:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(endpoint.address)
            sock.bind(endpoint.address)
        sock.listen(backlog)
    except OSError:
        sock.close()
        raise
    security.warn_if_insecure(endpoint.transport, endpoint.address)
    return Listener(sock, endpoint, security)


def dial(endpoint: Endpoint, security: SecurityProvider | None = None) -> Connection:
    """Connect to an endpoint, returning a :class:`Connection`."""
    security = security or NullSecurity()
    sock = _new_socket(endpoint)
    try:
        if endpoint.transport == TCP:
            sock.connect((endpoint.address, endpoint.port))
        else:
            sock.connect(endpoint.address)
    except OSError:
        sock.close()
        raise
    security.warn_if_insecure(endpoint.transport, endpoint.address)
    return Connection(security.wrap(sock, server=False))


def _new_socket(endpoint: Endpoint) -> socket.socket:
    if endpoint.transport == TCP:
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    return socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
