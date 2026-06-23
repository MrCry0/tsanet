"""Wire message schemas (brief 3.2).

Three message kinds are multiplexed over one connection:

- ``request``  (controller -> hub): an RPC call.
- ``response`` (hub -> controller): the reply to a request, matched by ``id``.
- ``event``    (hub -> controller): an unsolicited server push, e.g. live
  trace streaming.

Each message serializes to a MessagePack map; see :mod:`tsanet.protocol.codec`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union

from tsanet.common.errors import FrameError


class MessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"


class Status(str, Enum):
    OK = "ok"
    ERROR = "error"


@dataclass
class Request:
    id: int
    domain: str
    op: str
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": MessageType.REQUEST.value,
            "id": self.id,
            "domain": self.domain,
            "op": self.op,
            "args": self.args,
        }


@dataclass
class Response:
    id: int
    status: Status
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": MessageType.RESPONSE.value,
            "id": self.id,
            "status": Status(self.status).value,
            "data": self.data,
            "error": self.error,
        }


@dataclass
class Event:
    subscription_id: int
    domain: str
    op: str
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": MessageType.EVENT.value,
            "subscription_id": self.subscription_id,
            "domain": self.domain,
            "op": self.op,
            "data": self.data,
        }


Message = Union[Request, Response, Event]


def message_from_dict(obj: Any) -> Message:
    """Reconstruct a message from its decoded MessagePack map.

    Raises :class:`FrameError` if the map is malformed or the type is unknown.
    """
    if not isinstance(obj, dict):
        raise FrameError(f"message must be a map, got {type(obj).__name__}")
    raw_type = obj.get("type")
    try:
        message_type = MessageType(raw_type)
    except ValueError:
        raise FrameError(f"unknown message type: {raw_type!r}") from None

    try:
        if message_type is MessageType.REQUEST:
            return Request(
                id=obj["id"],
                domain=obj["domain"],
                op=obj["op"],
                args=obj.get("args") or {},
            )
        if message_type is MessageType.RESPONSE:
            return Response(
                id=obj["id"],
                status=Status(obj["status"]),
                data=obj.get("data"),
                error=obj.get("error"),
            )
        return Event(
            subscription_id=obj["subscription_id"],
            domain=obj["domain"],
            op=obj["op"],
            data=obj.get("data"),
        )
    except KeyError as missing:
        raise FrameError(f"missing field {missing} in {message_type.value}") from None
    except ValueError as bad:
        raise FrameError(str(bad)) from None
