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


class TransportError(TsanetError):
    """A network transport or wire-protocol failure."""


class ConnectionClosed(TransportError):
    """The peer closed the connection."""


class FrameError(TransportError):
    """A framed message could not be encoded or decoded."""


class SessionError(TsanetError):
    """A controller session could not be established or used."""


class SessionBusy(SessionError):
    """A controller session is already active and takeover was not requested."""


class DispatchError(TsanetError):
    """An RPC request could not be routed or its arguments were invalid."""
