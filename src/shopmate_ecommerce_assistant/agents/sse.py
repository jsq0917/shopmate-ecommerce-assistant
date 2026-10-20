"""SSE wire protocol (docs/06-api.md section 7).

Seven business event types, a monotonic ``sequence`` starting at 1, a single terminal
event (``done`` or ``error``) and a keepalive comment line. The serializer owns the
sequence counter so a caller cannot accidentally emit two events with the same id.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

SCHEMA_VERSION = "1.0"

EVENT_META = "meta"
EVENT_TOOL_STATUS = "tool_status"
EVENT_PRODUCT_CARD = "product_card"
EVENT_CITATION = "citation"
EVENT_DELTA = "delta"
EVENT_DONE = "done"
EVENT_ERROR = "error"


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One business event: a type plus its event-specific payload."""

    type: str
    data: dict[str, Any]


def meta_event(data: dict[str, Any]) -> StreamEvent:
    return StreamEvent(EVENT_META, data)


def tool_status_event(data: dict[str, Any]) -> StreamEvent:
    return StreamEvent(EVENT_TOOL_STATUS, data)


def product_card_event(data: dict[str, Any]) -> StreamEvent:
    return StreamEvent(EVENT_PRODUCT_CARD, data)


def citation_event(data: dict[str, Any]) -> StreamEvent:
    return StreamEvent(EVENT_CITATION, data)


def delta_event(data: dict[str, Any]) -> StreamEvent:
    return StreamEvent(EVENT_DELTA, data)


def done_event(data: dict[str, Any]) -> StreamEvent:
    return StreamEvent(EVENT_DONE, data)


def error_event(data: dict[str, Any]) -> StreamEvent:
    return StreamEvent(EVENT_ERROR, data)


class SSESerializer:
    """Turns :class:`StreamEvent` objects into SSE frames with a shared sequence."""

    def __init__(
        self,
        request_id: UUID,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._request_id = request_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sequence = 0

    @property
    def sequence(self) -> int:
        return self._sequence

    def frame(self, event: StreamEvent) -> str:
        """Serialize one event, incrementing the sequence and ``id``."""
        self._sequence += 1
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "event_id": str(self._sequence),
            "request_id": str(self._request_id),
            "sequence": self._sequence,
            "occurred_at": self._clock().isoformat(),
            "type": event.type,
            "data": event.data,
        }
        data = json.dumps(envelope, ensure_ascii=False)
        return f"id: {self._sequence}\nevent: {event.type}\ndata: {data}\n\n"

    @staticmethod
    def keepalive() -> str:
        """Return a comment-only keepalive line (not a business event)."""
        return ": keepalive\n\n"


__all__ = [
    "EVENT_CITATION",
    "EVENT_DELTA",
    "EVENT_DONE",
    "EVENT_ERROR",
    "EVENT_META",
    "EVENT_PRODUCT_CARD",
    "EVENT_TOOL_STATUS",
    "SCHEMA_VERSION",
    "SSESerializer",
    "StreamEvent",
    "citation_event",
    "delta_event",
    "done_event",
    "error_event",
    "meta_event",
    "product_card_event",
    "tool_status_event",
]
