"""Hub configuration (brief 7).

Loaded from ``~/.config/tsanet/hub.yaml`` by default; CLI flags override.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from tsanet.common.config import NetworkConfig, SecurityConfig, load_yaml

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "tsanet" / "hub.yaml"


class HubConfig(BaseModel):
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    #: Seconds between device hotplug rescans.
    poll_interval: float = 2.0

    @classmethod
    def load(cls, path: str | Path | None = DEFAULT_CONFIG_PATH) -> HubConfig:
        return cls(**load_yaml(path))
