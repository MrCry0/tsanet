"""Controller configuration.

Loaded from ``~/.config/tsanet/controller.yaml`` by default; CLI flags override.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from tsanet.common.config import NetworkConfig, SecurityConfig, load_yaml, save_yaml

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "tsanet" / "controller.yaml"


class ControllerConfig(BaseModel):
    network: NetworkConfig = Field(default_factory=lambda: NetworkConfig(mode="dial"))
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    refresh_interval_ms: int = Field(
        default=250, ge=10, description="Graph/stats update interval in milliseconds"
    )

    @classmethod
    def load(cls, path: str | Path | None = DEFAULT_CONFIG_PATH) -> ControllerConfig:
        return cls(**load_yaml(path))

    def save(self, path: str | Path) -> None:
        """Write this config to *path* as YAML."""
        save_yaml(path, self.model_dump(exclude_defaults=True))
