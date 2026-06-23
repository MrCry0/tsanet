"""Controller configuration (brief 7).

Loaded from ``~/.config/tsanet/controller.yaml`` by default; CLI flags override.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from tsanet.common.config import NetworkConfig, SecurityConfig, load_yaml

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "tsanet" / "controller.yaml"


class ControllerConfig(BaseModel):
    network: NetworkConfig = Field(default_factory=lambda: NetworkConfig(mode="dial"))
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    @classmethod
    def load(cls, path: str | Path | None = DEFAULT_CONFIG_PATH) -> ControllerConfig:
        return cls(**load_yaml(path))
