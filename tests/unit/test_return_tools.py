"""Unit tests for check_return_eligibility and create_return_request (fake ports)."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from shopmate_ecommerce_assistant.core.errors import ErrorCode
from shopmate_ecommerce_assistant.db.models.enums import OrderStatus, UserRole
from shopmate_ecommerce_assistant.tools.context import ConfirmationGrant, ToolContext
from shopmate_ecommerce_assistant.tools.return_tools import ReturnTools
from tests.support.fakes import (
    FakeIdempotencyStore,
    FakeOrderReader,
    FakeReturnWriter,
    InMemoryAudit,
    make_item,
    make_order,
)

SECRET = "test-secret-key-1234567890"
SHOP = uuid4()
NOW = datetime(2026, 10, 15, 8, 0, 0)


def _ctx(
    user,
    *,
    role=UserRole.SHOPPER,
    confirmation=None,
    conversation_id=None,
    idempotency_key=None,
):
    return ToolContext(
        shop_id=SHOP,
        actor_user_id=user,
        role=role,
        request_id=uuid4(),
        trace_id=uuid4(),
        confirmation=confirmation,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
    )


def _tools(reader, *, store, writer=None, audit=None):
    return ReturnTools(
        reader,
        store=store,
        writer=writer,
        token_secret=SECRET,
        audit=audit or InMemoryAudit(),
        clock=lambda: NOW,
    )


def _eligible_reader():
    order = make_order(user_id=uuid4(), order_no="SM-2026-00001")
    item = make_item(order.id)
    reader = FakeOrderReader(orders={order.id: order}, items={item.id: item})
    return order, item, reader


async def test_check_eligible_issues_token_with_invariants() -> None:
    order, item, reader = _eligible_reader()
    tools = _tools(reader, store=FakeIdempotencyStore())
    ctx = _ctx(order.user_id)

    result = await tools.check_return_eligibility(
        {
            "order_id": str(order.id),
            "order_item_id": str(item.id),
            "reason_code": "SIZE_OR_FIT",
        },
        context=ctx,
    )

    data = result.data
    assert result.ok is True
    assert data["decision"] == "eligible"
    assert data["decision_code"] == "RETURN_ELIGIBLE"
    assert data["eligible"] is True
    assert data["can_create_return_request"] is True
    assert data["handoff_required"] is False
    assert data["error_code"] is None
    assert data["eligibility_token"]
    assert data["eligibility_expires_at"] is not None
    assert data["rule_version"] == "demo-return-v1"


async def test_check_ineligible_for_unfinished_order() -> None:
    order = make_order(status=OrderStatus.SHIPPED, user_id=uuid4())
    item = make_item(order.id)
    reader = FakeOrderReader(orders={order.id: order}, items={item.id: item})
    tools = _tools(reader, store=FakeIdempotencyStore())

    result = await tools.check_return_eligibility(
        {"order_id": str(order.id), "order_item_id": str(item.id), "reason_code": "SIZE_OR_FIT"},
        context=_ctx(order.user_id),
    )

    assert result.ok is True
    assert result.data["decision"] == "ineligible"
    assert result.data["decision_code"] == "INVALID_STATE"
    assert result.data["can_create_return_request"] is False
    assert result.data["eligibility_token"] is None


async def test_check_missing_order_is_business_refusal_not_error() -> None:
    tools = _tools(FakeOrderReader(), store=FakeIdempotencyStore())
    result = await tools.check_return_eligibility(
        {
            "order_id": str(uuid4()),
            "order_item_id": str(uuid4()),
            "reason_code": "SIZE_OR_FIT",
        },
        context=_ctx(uuid4()),
    )
    assert result.ok is True
    assert result.data["decision"] == "ineligible"
    assert result.data["decision_code"] == "ORDER_NOT_FOUND"


async def test_create_requires_confirmation() -> None:
    order, item, reader = _eligible_reader()
    tools = _tools(reader, store=FakeIdempotencyStore(), writer=FakeReturnWriter())

    # A real token, but no server-side confirmation grant.
    check = await tools.check_return_eligibility(
        {"order_id": str(order.id), "order_item_id": str(item.id), "reason_code": "SIZE_OR_FIT"},
        context=_ctx(order.user_id),
    )
    result = await tools.create_return_request(
        {
            "order_id": str(order.id),
            "order_item_id": str(item.id),
            "reason_code": "SIZE_OR_FIT",
            "eligibility_token": check.data["eligibility_token"],
        },
        context=_ctx(order.user_id, idempotency_key="return-key-0000000001"),
    )
    assert result.error_code == ErrorCode.CONFIRMATION_REQUIRED.value


async def test_create_with_forged_token_is_eligibility_expired() -> None:
    order, item, reader = _eligible_reader()
    tools = _tools(reader, store=FakeIdempotencyStore(), writer=FakeReturnWriter())
    grant = ConfirmationGrant(
        operation="create_return_request",
        order_id=order.id,
        order_item_id=item.id,
        reason_code="SIZE_OR_FIT",
        expires_at=NOW + timedelta(minutes=10),
    )
    result = await tools.create_return_request(
        {
            "order_id": str(order.id),
            "order_item_id": str(item.id),
            "reason_code": "SIZE_OR_FIT",
            "eligibility_token": "v1." + "f" * 20 + "." + "f" * 20,
        },
        context=_ctx(order.user_id, confirmation=grant, idempotency_key="return-key-0000000002"),
    )
    assert result.error_code == ErrorCode.ELIGIBILITY_EXPIRED.value


async def test_create_submits_only_submitted() -> None:
    order, item, reader = _eligible_reader()
    store = FakeIdempotencyStore()
    writer = FakeReturnWriter(store=store)
    audit = InMemoryAudit()
    tools = _tools(reader, store=store, writer=writer, audit=audit)
    check = await tools.check_return_eligibility(
        {"order_id": str(order.id), "order_item_id": str(item.id), "reason_code": "SIZE_OR_FIT"},
        context=_ctx(order.user_id),
    )
    grant = ConfirmationGrant(
        operation="create_return_request",
        order_id=order.id,
        order_item_id=item.id,
        reason_code="SIZE_OR_FIT",
        expires_at=NOW + timedelta(minutes=10),
    )
    result = await tools.create_return_request(
        {
            "order_id": str(order.id),
            "order_item_id": str(item.id),
            "reason_code": "SIZE_OR_FIT",
            "eligibility_token": check.data["eligibility_token"],
        },
        context=_ctx(order.user_id, confirmation=grant, idempotency_key="return-key-0000000003"),
    )

    assert result.ok is True
    assert result.data["status"] == "submitted"
    assert result.data["refund_status"] == "not_created"
    assert "退款" in result.data["notice"]
    assert len(writer.created) == 1
    assert writer.created[0].status == "submitted"
    assert writer.tool_calls[0].tool_name == "create_return_request"


async def test_create_is_idempotent_and_reuses_tool_call_id() -> None:
    order, item, reader = _eligible_reader()
    store = FakeIdempotencyStore()
    writer = FakeReturnWriter(store=store)
    audit = InMemoryAudit()
    tools = _tools(reader, store=store, writer=writer, audit=audit)
    check = await tools.check_return_eligibility(
        {"order_id": str(order.id), "order_item_id": str(item.id), "reason_code": "SIZE_OR_FIT"},
        context=_ctx(order.user_id),
    )
    grant = ConfirmationGrant(
        operation="create_return_request",
        order_id=order.id,
        order_item_id=item.id,
        reason_code="SIZE_OR_FIT",
        expires_at=NOW + timedelta(minutes=10),
    )
    payload = {
        "order_id": str(order.id),
        "order_item_id": str(item.id),
        "reason_code": "SIZE_OR_FIT",
        "eligibility_token": check.data["eligibility_token"],
    }

    first = await tools.create_return_request(
        payload,
        context=_ctx(order.user_id, confirmation=grant, idempotency_key="return-key-0000000004"),
    )
    second = await tools.create_return_request(
        payload,
        context=_ctx(order.user_id, confirmation=grant, idempotency_key="return-key-0000000004"),
    )

    assert first.ok is True and second.ok is True
    assert second.data["return_request_id"] == first.data["return_request_id"]
    assert second.idempotent_replay is True
    assert second.tool_call_id == first.tool_call_id
    assert len(writer.created) == 1
    # No second tool_calls row: the writer only recorded the first.
    assert len(writer.tool_calls) == 1


async def test_create_same_key_different_params_is_conflict() -> None:
    order, item, reader = _eligible_reader()
    store = FakeIdempotencyStore()
    writer = FakeReturnWriter(store=store)
    tools = _tools(reader, store=store, writer=writer)
    check = await tools.check_return_eligibility(
        {"order_id": str(order.id), "order_item_id": str(item.id), "reason_code": "SIZE_OR_FIT"},
        context=_ctx(order.user_id),
    )
    grant = ConfirmationGrant(
        operation="create_return_request",
        order_id=order.id,
        order_item_id=item.id,
        reason_code="SIZE_OR_FIT",
        expires_at=NOW + timedelta(minutes=10),
    )
    key = "return-key-0000000005"
    base = {
        "order_id": str(order.id),
        "order_item_id": str(item.id),
        "reason_code": "SIZE_OR_FIT",
        "eligibility_token": check.data["eligibility_token"],
    }
    await tools.create_return_request(
        base, context=_ctx(order.user_id, confirmation=grant, idempotency_key=key)
    )
    changed = dict(base, reason_code="NO_LONGER_NEEDED")
    result = await tools.create_return_request(
        changed, context=_ctx(order.user_id, confirmation=grant, idempotency_key=key)
    )
    assert result.error_code == ErrorCode.IDEMPOTENCY_CONFLICT.value


async def test_create_rechecks_rules_and_blocks_when_order_changed() -> None:
    order = make_order(status=OrderStatus.DELIVERED, user_id=uuid4())
    item = make_item(order.id)
    reader = FakeOrderReader(orders={order.id: order}, items={item.id: item})
    store = FakeIdempotencyStore()
    tools = _tools(reader, store=store, writer=FakeReturnWriter(store=store))
    check = await tools.check_return_eligibility(
        {"order_id": str(order.id), "order_item_id": str(item.id), "reason_code": "SIZE_OR_FIT"},
        context=_ctx(order.user_id),
    )
    # Order gets cancelled between check and write.
    reader.orders[order.id] = make_order(
        id=order.id, user_id=order.user_id, status=OrderStatus.CANCELLED
    )
    grant = ConfirmationGrant(
        operation="create_return_request",
        order_id=order.id,
        order_item_id=item.id,
        reason_code="SIZE_OR_FIT",
        expires_at=NOW + timedelta(minutes=10),
    )
    result = await tools.create_return_request(
        {
            "order_id": str(order.id),
            "order_item_id": str(item.id),
            "reason_code": "SIZE_OR_FIT",
            "eligibility_token": check.data["eligibility_token"],
        },
        context=_ctx(order.user_id, confirmation=grant, idempotency_key="return-key-0000000006"),
    )
    assert result.error_code == ErrorCode.RETURN_NOT_ALLOWED.value
    assert store.failed


async def test_create_writer_conflict_is_duplicate_return() -> None:
    order, item, reader = _eligible_reader()
    store = FakeIdempotencyStore()
    writer = FakeReturnWriter(store=store, conflict=True)
    tools = _tools(reader, store=store, writer=writer)
    check = await tools.check_return_eligibility(
        {"order_id": str(order.id), "order_item_id": str(item.id), "reason_code": "SIZE_OR_FIT"},
        context=_ctx(order.user_id),
    )
    grant = ConfirmationGrant(
        operation="create_return_request",
        order_id=order.id,
        order_item_id=item.id,
        reason_code="SIZE_OR_FIT",
        expires_at=NOW + timedelta(minutes=10),
    )
    result = await tools.create_return_request(
        {
            "order_id": str(order.id),
            "order_item_id": str(item.id),
            "reason_code": "SIZE_OR_FIT",
            "eligibility_token": check.data["eligibility_token"],
        },
        context=_ctx(order.user_id, confirmation=grant, idempotency_key="return-key-0000000007"),
    )
    assert result.error_code == ErrorCode.DUPLICATE_RETURN.value


async def test_support_cannot_create_return() -> None:
    order, item, reader = _eligible_reader()
    tools = _tools(reader, store=FakeIdempotencyStore(), writer=FakeReturnWriter())
    grant = ConfirmationGrant(
        operation="create_return_request",
        order_id=order.id,
        order_item_id=item.id,
        reason_code="SIZE_OR_FIT",
        expires_at=NOW + timedelta(minutes=10),
    )
    result = await tools.create_return_request(
        {
            "order_id": str(order.id),
            "order_item_id": str(item.id),
            "reason_code": "SIZE_OR_FIT",
            "eligibility_token": "v1." + "f" * 20 + "." + "f" * 20,
        },
        context=_ctx(
            order.user_id,
            role=UserRole.SUPPORT,
            confirmation=grant,
            idempotency_key="return-key-0000000008",
        ),
    )
    assert result.error_code == ErrorCode.FORBIDDEN.value


async def test_retry_with_same_key_after_confirmation_succeeds() -> None:
    order, item, reader = _eligible_reader()
    store = FakeIdempotencyStore()
    writer = FakeReturnWriter(store=store)
    tools = _tools(reader, store=store, writer=writer)
    key = "return-key-0000000009"

    check = await tools.check_return_eligibility(
        {"order_id": str(order.id), "order_item_id": str(item.id), "reason_code": "SIZE_OR_FIT"},
        context=_ctx(order.user_id),
    )
    payload = {
        "order_id": str(order.id),
        "order_item_id": str(item.id),
        "reason_code": "SIZE_OR_FIT",
        "eligibility_token": check.data["eligibility_token"],
    }

    # No confirmation grant: a retryable CONFIRMATION_REQUIRED must release the claim.
    first = await tools.create_return_request(
        payload, context=_ctx(order.user_id, idempotency_key=key)
    )
    assert first.error_code == ErrorCode.CONFIRMATION_REQUIRED.value

    # Confirm and retry with the same key: it must succeed, not replay a stale failure.
    grant = ConfirmationGrant(
        operation="create_return_request",
        order_id=order.id,
        order_item_id=item.id,
        reason_code="SIZE_OR_FIT",
        expires_at=NOW + timedelta(minutes=10),
    )
    second = await tools.create_return_request(
        payload, context=_ctx(order.user_id, confirmation=grant, idempotency_key=key)
    )
    assert second.ok is True
    assert second.data["status"] == "submitted"
    assert len(writer.created) == 1

    stored = store.records[(order.user_id, key)]
    assert stored.status == "succeeded"


async def test_non_retryable_failure_still_blocks_same_key() -> None:
    order, item, reader = _eligible_reader()
    store = FakeIdempotencyStore()
    tools = _tools(reader, store=store, writer=FakeReturnWriter(store=store))
    check = await tools.check_return_eligibility(
        {"order_id": str(order.id), "order_item_id": str(item.id), "reason_code": "SIZE_OR_FIT"},
        context=_ctx(order.user_id),
    )
    assert check.data["eligible"] is True

    # The signature slips outside the 7-day window after the eligibility check.
    reader.items[item.id] = make_item(order.id, id=item.id, delivered_at=NOW - timedelta(days=8))

    grant = ConfirmationGrant(
        operation="create_return_request",
        order_id=order.id,
        order_item_id=item.id,
        reason_code="SIZE_OR_FIT",
        expires_at=NOW + timedelta(minutes=10),
    )
    key = "return-key-0000000010"
    payload = {
        "order_id": str(order.id),
        "order_item_id": str(item.id),
        "reason_code": "SIZE_OR_FIT",
        "eligibility_token": check.data["eligibility_token"],
    }

    first = await tools.create_return_request(
        payload, context=_ctx(order.user_id, confirmation=grant, idempotency_key=key)
    )
    assert first.error_code == ErrorCode.RETURN_WINDOW_EXPIRED.value

    # RETURN_WINDOW_EXPIRED is non-retryable: the same key must keep the safe failure.
    second = await tools.create_return_request(
        payload, context=_ctx(order.user_id, confirmation=grant, idempotency_key=key)
    )
    assert second.error_code == ErrorCode.RETURN_WINDOW_EXPIRED.value
