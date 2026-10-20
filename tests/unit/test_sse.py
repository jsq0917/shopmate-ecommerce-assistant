"""SSE wire protocol tests: frame format, monotonic sequence and terminal events."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from shopmate_ecommerce_assistant.agents.sse import (
    EVENT_CITATION,
    EVENT_DELTA,
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_META,
    EVENT_PRODUCT_CARD,
    EVENT_TOOL_STATUS,
    SCHEMA_VERSION,
    SSESerializer,
    StreamEvent,
    citation_event,
    delta_event,
    done_event,
    error_event,
    meta_event,
    product_card_event,
    tool_status_event,
)


def _fixed_clock() -> datetime:
    return datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)


def test_serializer_increments_sequence_and_emits_id() -> None:
    serializer = SSESerializer(uuid4(), clock=_fixed_clock)

    first = serializer.frame(meta_event({"route": "smalltalk_or_unknown"}))
    second = serializer.frame(delta_event({"text": "你好"}))

    assert serializer.sequence == 2
    assert first.startswith("id: 1\n")
    assert second.startswith("id: 2\n")


def test_frame_is_valid_sse_with_json_payload() -> None:
    serializer = SSESerializer(uuid4(), clock=_fixed_clock)
    frame = serializer.frame(meta_event({"conversation_id": "abc"}))

    lines = frame.split("\n")
    assert lines[0] == "id: 1"
    assert lines[1] == "event: meta"
    assert lines[2].startswith("data: ")
    assert lines[3:] == ["", ""]  # SSE terminates a frame with a blank line

    payload = json.loads(lines[2][len("data: ") :])
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["sequence"] == 1
    assert payload["type"] == "meta"
    assert payload["event_id"] == "1"
    assert payload["data"]["conversation_id"] == "abc"
    assert "request_id" in payload


def test_all_seven_event_types_have_stable_names() -> None:
    assert meta_event({}).type == EVENT_META
    assert tool_status_event({}).type == EVENT_TOOL_STATUS
    assert product_card_event({}).type == EVENT_PRODUCT_CARD
    assert citation_event({}).type == EVENT_CITATION
    assert delta_event({}).type == EVENT_DELTA
    assert done_event({}).type == EVENT_DONE
    assert error_event({}).type == EVENT_ERROR


def test_keepalive_is_a_comment_without_sequence() -> None:
    serializer = SSESerializer(uuid4())
    assert serializer.keepalive() == ": keepalive\n\n"
    assert serializer.sequence == 0  # keepalive does not advance the sequence


def test_stream_event_is_immutable_and_carries_payload() -> None:
    event = StreamEvent(type="delta", data={"text": "x"})
    assert event.type == "delta"
    assert event.data == {"text": "x"}
