"""Unit tests for create_handoff_ticket (fake ports)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from shopmate_ecommerce_assistant.core.errors import ErrorCode
from shopmate_ecommerce_assistant.db.models.enums import UserRole
from shopmate_ecommerce_assistant.domain.orders.models import ConversationSnapshot
from shopmate_ecommerce_assistant.safety.risk import RiskLevel
from shopmate_ecommerce_assistant.tools.context import RiskContext, ToolContext
from shopmate_ecommerce_assistant.tools.handoff_tools import HandoffTools
from tests.support.fakes import (
    FakeHandoffWriter,
    FakeIdempotencyStore,
    FakeOrderReader,
    InMemoryAudit,
)

SHOP = uuid4()
NOW = datetime(2026, 10, 15, 8, 0, 0)


def _ctx(user, *, role=UserRole.SHOPPER, risk=None, conversation_id=None, idempotency_key=None):
    return ToolContext(
        shop_id=SHOP,
        actor_user_id=user,
        role=role,
        request_id=uuid4(),
        trace_id=uuid4(),
        risk_context=risk,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
    )


def _tools(reader, *, store, writer=None, audit=None):
    return HandoffTools(
        reader,
        store=store,
        writer=writer,
        audit=audit or InMemoryAudit(),
        clock=lambda: NOW,
    )


async def test_create_open_ticket_with_resolved_risk() -> None:
    user = uuid4()
    conv = ConversationSnapshot(id=uuid4(), user_id=user)
    reader = FakeOrderReader(conversations={conv.id: conv})
    store = FakeIdempotencyStore()
    writer = FakeHandoffWriter(store=store)
    tools = _tools(reader, store=store, writer=writer)

    result = await tools.create_handoff_ticket(
        {
            "conversation_id": str(conv.id),
            "reason_code": "LEGAL_OR_REGULATORY",
            "summary_redacted": "用户要求投诉并提及法律途径。",
        },
        context=_ctx(user, conversation_id=conv.id, idempotency_key="handoff-key-000000001"),
    )

    assert result.ok is True
    assert result.data["status"] == "open"
    assert result.data["risk_level"] == "critical"
    assert result.data["priority"] == 1
    assert result.data["primary_reason_code"] == "LEGAL_OR_REGULATORY"
    assert result.data["expected_response"]
    assert "退款" in result.data["expected_response"] or "赔偿" in result.data["expected_response"]
    assert len(writer.created) == 1


async def test_risk_level_is_not_downgradable() -> None:
    user = uuid4()
    conv = ConversationSnapshot(id=uuid4(), user_id=user)
    reader = FakeOrderReader(conversations={conv.id: conv})
    store = FakeIdempotencyStore()
    writer = FakeHandoffWriter(store=store)
    risk = RiskContext(level=RiskLevel.CRITICAL, codes=("PERSONAL_SAFETY",))
    tools = _tools(reader, store=store, writer=writer)

    result = await tools.create_handoff_ticket(
        {
            "conversation_id": str(conv.id),
            "reason_code": "COMPLAINT",
            "summary_redacted": "强烈不满。",
        },
        context=_ctx(
            user,
            risk=risk,
            conversation_id=conv.id,
            idempotency_key="handoff-key-000000002",
        ),
    )

    assert result.data["risk_level"] == "critical"
    assert result.data["primary_reason_code"] == "PERSONAL_SAFETY"


async def test_summary_pii_is_masked() -> None:
    user = uuid4()
    conv = ConversationSnapshot(id=uuid4(), user_id=user)
    reader = FakeOrderReader(conversations={conv.id: conv})
    store = FakeIdempotencyStore()
    writer = FakeHandoffWriter(store=store)
    tools = _tools(reader, store=store, writer=writer)

    result = await tools.create_handoff_ticket(
        {
            "conversation_id": str(conv.id),
            "reason_code": "COMPLAINT",
            "summary_redacted": "我的电话是 13812345678，请回电。",
        },
        context=_ctx(user, conversation_id=conv.id, idempotency_key="handoff-key-000000003"),
    )

    assert result.ok is True
    stored = writer.created[0]
    # The raw phone number must not appear in the stored summary.
    assert "13812345678" not in writer.tool_calls[0].input_redacted["summary_redacted"]
    assert stored.status == "open"


async def test_conversation_not_found() -> None:
    tools = _tools(FakeOrderReader(), store=FakeIdempotencyStore())
    result = await tools.create_handoff_ticket(
        {
            "conversation_id": str(uuid4()),
            "reason_code": "COMPLAINT",
            "summary_redacted": "投诉。",
        },
        context=_ctx(uuid4(), idempotency_key="handoff-key-000000004"),
    )
    assert result.error_code == ErrorCode.CONVERSATION_NOT_FOUND.value


async def test_unknown_reason_is_validation_error() -> None:
    user = uuid4()
    conv = ConversationSnapshot(id=uuid4(), user_id=user)
    reader = FakeOrderReader(conversations={conv.id: conv})
    tools = _tools(reader, store=FakeIdempotencyStore())
    result = await tools.create_handoff_ticket(
        {
            "conversation_id": str(conv.id),
            "reason_code": "NOT_A_REAL_RISK",
            "summary_redacted": "x",
        },
        context=_ctx(user, idempotency_key="handoff-key-000000005"),
    )
    assert result.error_code == ErrorCode.VALIDATION_ERROR.value


async def test_idempotent_replay_same_ticket() -> None:
    user = uuid4()
    conv = ConversationSnapshot(id=uuid4(), user_id=user)
    reader = FakeOrderReader(conversations={conv.id: conv})
    store = FakeIdempotencyStore()
    writer = FakeHandoffWriter(store=store)
    tools = _tools(reader, store=store, writer=writer)
    payload = {
        "conversation_id": str(conv.id),
        "reason_code": "COMPLAINT",
        "summary_redacted": "投诉。",
    }
    first = await tools.create_handoff_ticket(
        payload,
        context=_ctx(user, conversation_id=conv.id, idempotency_key="handoff-key-000000006"),
    )
    second = await tools.create_handoff_ticket(
        payload,
        context=_ctx(user, conversation_id=conv.id, idempotency_key="handoff-key-000000006"),
    )

    assert second.idempotent_replay is True
    assert second.data["ticket_id"] == first.data["ticket_id"]
    assert second.tool_call_id == first.tool_call_id
    assert len(writer.created) == 1


async def test_idempotency_conflict_on_different_summary() -> None:
    user = uuid4()
    conv = ConversationSnapshot(id=uuid4(), user_id=user)
    reader = FakeOrderReader(conversations={conv.id: conv})
    store = FakeIdempotencyStore()
    tools = _tools(reader, store=store, writer=FakeHandoffWriter(store=store))
    key = "handoff-key-000000007"
    await tools.create_handoff_ticket(
        {
            "conversation_id": str(conv.id),
            "reason_code": "COMPLAINT",
            "summary_redacted": "投诉 A",
        },
        context=_ctx(user, conversation_id=conv.id, idempotency_key=key),
    )
    result = await tools.create_handoff_ticket(
        {
            "conversation_id": str(conv.id),
            "reason_code": "COMPLAINT",
            "summary_redacted": "投诉 B",
        },
        context=_ctx(user, conversation_id=conv.id, idempotency_key=key),
    )
    assert result.error_code == ErrorCode.IDEMPOTENCY_CONFLICT.value


async def test_extra_risk_level_field_is_rejected() -> None:
    user = uuid4()
    conv = ConversationSnapshot(id=uuid4(), user_id=user)
    reader = FakeOrderReader(conversations={conv.id: conv})
    tools = _tools(reader, store=FakeIdempotencyStore())
    result = await tools.create_handoff_ticket(
        {
            "conversation_id": str(conv.id),
            "reason_code": "COMPLAINT",
            "summary_redacted": "投诉。",
            "risk_level": "low",
        },
        context=_ctx(user, idempotency_key="handoff-key-000000008"),
    )
    assert result.error_code == ErrorCode.VALIDATION_ERROR.value


async def test_handoff_retry_after_transient_writer_failure() -> None:
    user = uuid4()
    conv = ConversationSnapshot(id=uuid4(), user_id=user)
    reader = FakeOrderReader(conversations={conv.id: conv})
    store = FakeIdempotencyStore()
    writer = FakeHandoffWriter(store=store, fail_attempts=1)
    tools = _tools(reader, store=store, writer=writer)
    key = "handoff-key-000000009"
    payload = {
        "conversation_id": str(conv.id),
        "reason_code": "COMPLAINT",
        "summary_redacted": "投诉。",
    }

    # A transient writer failure releases the claim instead of poisoning the key.
    first = await tools.create_handoff_ticket(
        payload, context=_ctx(user, conversation_id=conv.id, idempotency_key=key)
    )
    assert first.error_code == ErrorCode.UPSTREAM_UNAVAILABLE.value

    # The same key retries successfully and still creates exactly one ticket.
    second = await tools.create_handoff_ticket(
        payload, context=_ctx(user, conversation_id=conv.id, idempotency_key=key)
    )
    assert second.ok is True
    assert len(writer.created) == 1
    assert store.records[(user, key)].status == "succeeded"
