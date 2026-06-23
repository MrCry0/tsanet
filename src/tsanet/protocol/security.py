"""Pluggable security providers (brief 3.3).

A ``SecurityProvider`` wraps the raw socket so the transport layer does not
need rework as security hardens across phases:

- Phase A (here): :class:`NullSecurity`, plaintext, warning on non-loopback.
- Phase B: a shared-secret token exchanged at session start.
- Phase C: TLS plus the token, with a cert-generation helper.

Only Phase A is implemented; the interface is shaped so later phases slot in
without touching :mod:`tsanet.protocol.transport`.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger("tsanet.protocol")


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
