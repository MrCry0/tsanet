"""Shared configuration models (brief 7).

Hub and controller take the same network and security shapes. Values come
from a YAML file and are overridable by CLI flags (handled by each program's
CLI). Models are validated with pydantic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, model_validator

from tsanet.common.errors import SecurityNotImplementedError
from tsanet.protocol.security import NullSecurity, SecurityProvider, TokenSecurity
from tsanet.protocol.transport import TCP, Endpoint


class NetworkConfig(BaseModel):
    mode: Literal["listen", "dial"] = "listen"
    transport: Literal["tcp", "unix"] = "tcp"
    address: str = "0.0.0.0"
    port: int | None = 7777

    @model_validator(mode="after")
    def _require_port_for_tcp(self) -> NetworkConfig:
        if self.transport == TCP and self.port is None:
            raise ValueError("tcp transport requires a port")
        return self

    def endpoint(self) -> Endpoint:
        return Endpoint(
            transport=self.transport,
            address=self.address,
            port=self.port if self.transport == TCP else None,
        )


class SecurityConfig(BaseModel):
    mode: Literal["none", "token", "tls-token"] = "none"
    token: str | None = None
    tls_cert: str | None = None
    tls_key: str | None = None
    tls_ca: str | None = None

    @model_validator(mode="after")
    def _require_secrets(self) -> SecurityConfig:
        if self.mode in ("token", "tls-token") and not self.token:
            raise ValueError("a token is required when security mode is not 'none'")
        if self.mode == "tls-token" and not (self.tls_cert and self.tls_key):
            raise ValueError("tls-token mode requires tls_cert and tls_key")
        return self

    def build_provider(self) -> SecurityProvider:
        """Construct the :class:`SecurityProvider` for this configuration.

        Raises :class:`SecurityNotImplementedError` for modes that are
        validated (so config files can specify them) but have no provider
        implemented yet.
        """
        if self.mode == "none":
            return NullSecurity()
        if self.mode == "token":
            assert self.token is not None  # enforced by _require_secrets
            return TokenSecurity(self.token)
        if self.mode == "tls-token":
            raise SecurityNotImplementedError(
                "security mode 'tls-token' is not implemented yet; use 'token' or 'none'"
            )
        raise AssertionError(f"unhandled security mode: {self.mode!r}")


def load_yaml(path: str | Path | None) -> dict[str, Any]:
    """Load a YAML mapping from ``path``; return ``{}`` if it does not exist."""
    if path is None:
        return {}
    file = Path(path)
    if not file.exists():
        return {}
    with file.open() as handle:
        return yaml.safe_load(handle) or {}
