"""Pluggable security providers (brief 3.3).

A ``SecurityProvider`` wraps the raw socket so the transport layer does not
need rework as security hardens across phases:

- Phase A: :class:`NullSecurity`, plaintext, warning on non-loopback.
- Phase B (here): :class:`TokenSecurity`, a shared-secret token exchanged
  immediately after the raw socket connects, before any framed messages.
- Phase C: TLS plus the token, with a cert-generation helper. Not
  implemented yet; see :meth:`tsanet.common.config.SecurityConfig.build_provider`.

The interface is shaped so later phases slot in without touching
:mod:`tsanet.protocol.transport`.
"""

from __future__ import annotations

import contextlib
import hmac
import logging
import struct
from typing import Protocol, runtime_checkable

from tsanet.common.errors import AuthenticationError, ConnectionClosed

logger = logging.getLogger("tsanet.protocol")

_TOKEN_LEN = struct.Struct(">H")
_ACK_OK = b"\x01"
_ACK_FAIL = b"\x00"
_HANDSHAKE_TIMEOUT = 5.0


def is_loopback(address: str) -> bool:
    """True if ``address`` refers only to the local host."""
    return address == "localhost" or address == "::1" or address.startswith("127.")


@runtime_checkable
class SecurityProvider(Protocol):
    """Wraps a connected socket and reports insecure endpoints."""

    def wrap(self, sock, *, server: bool):
        """Return a socket-like object layered with this provider's security."""
        ...

    def warn_if_insecure(self, transport: str, address: str) -> None:
        """Emit a warning if the endpoint exposes traffic without protection."""
        ...


class NullSecurity:
    """No security: the socket is used as-is, in the clear."""

    def wrap(self, sock, *, server: bool = False):
        return sock

    def warn_if_insecure(self, transport: str, address: str) -> None:
        if transport == "tcp" and not is_loopback(address):
            logger.warning(
                "NullSecurity in use: traffic on %s is unencrypted and unauthenticated",
                address,
            )


class TokenSecurity:
    """Shared-secret token exchanged right after the socket connects.

    The dialing side sends its token; the accepting side compares it to its
    own configured token with a constant-time check and replies with a
    one-byte ack. A mismatch closes the socket and raises
    :class:`AuthenticationError` on both ends.

    This authenticates the peer but does not encrypt anything -- the token
    and all subsequent traffic are still sent in the clear. Combine with TLS
    (``tls-token`` mode, not implemented yet) for confidentiality.
    """

    def __init__(self, token: str) -> None:
        encoded = token.encode("utf-8")
        if len(encoded) > 0xFFFF:
            raise ValueError("token is too long to encode (max 65535 bytes)")
        self._token = encoded

    def wrap(self, sock, *, server: bool = False):
        original_timeout = sock.gettimeout()
        sock.settimeout(_HANDSHAKE_TIMEOUT)
        try:
            if server:
                self._verify(sock)
            else:
                self._present(sock)
        finally:
            # On failure the socket is already closed by _verify/_present,
            # so resetting the timeout would raise; ignore that case.
            with contextlib.suppress(OSError):
                sock.settimeout(original_timeout)
        return sock

    def warn_if_insecure(self, transport: str, address: str) -> None:
        if transport == "tcp" and not is_loopback(address):
            logger.warning(
                "TokenSecurity in use: the token and traffic on %s are sent in "
                "the clear (token mode authenticates, it does not encrypt)",
                address,
            )

    def _present(self, sock) -> None:
        sock.sendall(_TOKEN_LEN.pack(len(self._token)) + self._token)
        if _recv_exact(sock, 1) != _ACK_OK:
            sock.close()
            raise AuthenticationError("hub rejected the security token")

    def _verify(self, sock) -> None:
        (length,) = _TOKEN_LEN.unpack(_recv_exact(sock, _TOKEN_LEN.size))
        presented = _recv_exact(sock, length)
        if hmac.compare_digest(presented, self._token):
            sock.sendall(_ACK_OK)
        else:
            sock.sendall(_ACK_FAIL)
            sock.close()
            raise AuthenticationError("peer presented an invalid security token")


def _recv_exact(sock, count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionClosed("peer closed the connection during the security handshake")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
