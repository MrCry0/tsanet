"""Error types shared across the device, hub, and controller layers."""

from __future__ import annotations


class TsanetError(Exception):
    """Base class for all tsanet errors."""


class DeviceError(TsanetError):
    """A tinySA device or its serial link misbehaved."""


class DeviceTimeout(DeviceError):
    """The device did not produce the expected response in time."""


class ProtocolError(DeviceError):
    """The device response did not match the expected wire format."""
