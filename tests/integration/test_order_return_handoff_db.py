"""Integration tests for order, return and handoff tools against PostgreSQL.

These prove the permission boundary and idempotency at the database layer, where the
unique indexes and composite foreign keys are the final arbiter.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa

from shopmate_ecommerce_assistant.core.errors import ErrorCode
from shopmate_ecommerce_assistant.db.models import (
    AuditEvent,
    Conversation,
    HandoffTicket,
    IdempotencyRecord,
    Order,
    OrderItem,
    OrderStatus,
    ReturnReasonCode,
    ReturnRequest,
    ReturnStatus,
    Shipment,
    ShipmentEvent,
    Shop,
    ToolCall,
    User,
    UserRole,
)
from shopmate_ecommerce_assistant.db.repositories.audit import AuditRepository
from shopmate_ecommerce_assistant.db.repositories.handoff import HandoffRepository
from shopmate_ecommerce_assistant.db.repositories.idempotency import IdempotencyRepository
from shopmate_ecommerce_assistant.db.repositories.orders import OrderRepository
from shopmate_ecommerce_assistant.db.repositories.returns import ReturnRepository
from shopmate_ecommerce_assistant.tools.context import ConfirmationGrant, ToolContext
from shopmate_ecommerce_assistant.tools.handoff_tools import HandoffTools
from shopmate_ecommerce_assistant.tools.order_tools import OrderTools
from shopmate_ecommerce_assistant.tools.return_tools import ReturnTools
from shopmate_ecommerce_assistant.tools.runtime import ToolRuntime

pytestmark = pytest.mark.integration

SECRET = "integration-secret-key-123456"
NOW = datetime(2026, 10, 15, 8, 0, 0, tzinfo=UTC)


async def _seed(session) -> dict:
    shop = Shop(id=uuid4(), name="集成测试店铺")
    user_a = User(id=uuid4(), shop_id=shop.id, email_ci="a@example.invalid", password_hash="!x")
    user_b = User(id=uuid4(), shop_id=shop.id, email_ci="b@example.invalid", password_hash="!x")
    order = Order(
        id=uuid4(),
        shop_id=shop.id,
        user_id=user_a.id,
        order_no="IT-2026-0001",
        status=OrderStatus.DELIVERED,
        total_cents=29_900,
        currency="CNY",
        placed_at=NOW - timedelta(days=5),
        delivered_at=NOW - timedelta(days=2),
        source_system="mock_oms",
        is_synthetic=True,
    )
    item = OrderItem(
        id=uuid4(),
        shop_id=shop.id,
        order_id=order.id,
        sku_snapshot="IT-001",
        title_snapshot="集成测试商品",
        category_snapshot="耳机",
        is_returnable_snapshot=True,
        quantity=1,
        unit_price_cents=29_900,
        line_total_cents=29_900,
        status="active",
        delivered_at=NOW - timedelta(days=2),
    )
    shipment = Shipment(
        id=uuid4(),
        shop_id=shop.id,
        order_id=order.id,
        carrier="顺捷速运（合成）",
        tracking_no_masked="IT****0001",
        status="in_transit",
        shipped_at=NOW - timedelta(days=4),
        source_system="mock_oms",
    )
    event = ShipmentEvent(
        id=uuid4(),
        shop_id=shop.id,
        shipment_id=shipment.id,
        sequence_no=1,
        status="in_transit",
        description="已到达转运中心",
        occurred_at=NOW - timedelta(days=3),
    )
    conversation = Conversation(id=uuid4(), shop_id=shop.id, user_id=user_a.id, title="集成会话")

    session.add_all([shop, user_a, user_b, order, item, shipment, event, conversation])
    await session.commit()
    return {
        "shop": shop,
        "user_a": user_a,
        "user_b": user_b,
        "order": order,
        "item": item,
        "shipment": shipment,
        "conversation": conversation,
    }


async def _cleanup(session, shop_id) -> None:
    """Delete everything this test's shop created, in FK-safe (child-first) order."""
    tables = (
        AuditEvent,
        ToolCall,
        HandoffTicket,
        IdempotencyRecord,
        ReturnRequest,
        ShipmentEvent,
        Shipment,
        OrderItem,
        Order,
        Conversation,
        User,
        Shop,
    )
    for model in tables:
        if model is Shop:
            await session.execute(sa.delete(model).where(model.id == shop_id))
        else:
            await session.execute(sa.delete(model).where(model.shop_id == shop_id))
    await session.commit()


@pytest.fixture
async def seeded(session):
    """Yield a fresh shop/user/order/conversation and remove it afterwards.

    This keeps the shared demo database free of test-only rows so the seed and catalog
    integration tests, which assert global counts, stay deterministic.
    """
    data = await _seed(session)
    try:
        yield data
    finally:
        await _cleanup(session, data["shop"].id)


def _ctx(
    user,
    *,
    role=UserRole.SHOPPER,
    confirmation=None,
    conversation_id=None,
    idempotency_key=None,
):
    return ToolContext(
        shop_id=user.shop_id,
        actor_user_id=user.id,
        role=role,
        request_id=uuid4(),
        trace_id=uuid4(),
        confirmation=confirmation,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
    )


def _order_tools(session):
    reader = OrderRepository(session)
    audit = AuditRepository(session)
    return OrderTools(reader, runtime=ToolRuntime(audit))


def _return_tools(session, *, clock=None):
    reader = OrderRepository(session)
    store = IdempotencyRepository(session)
    audit = AuditRepository(session)
    writer = ReturnRepository(session)
    return ReturnTools(
        reader,
        store=store,
        writer=writer,
        token_secret=SECRET,
        audit=audit,
        runtime=ToolRuntime(audit),
        clock=clock or (lambda: NOW),
    )


def _handoff_tools(session):
    reader = OrderRepository(session)
    store = IdempotencyRepository(session)
    audit = AuditRepository(session)
    writer = HandoffRepository(session)
    return HandoffTools(
        reader,
        store=store,
        writer=writer,
        audit=audit,
        runtime=ToolRuntime(audit),
        clock=lambda: NOW,
    )


async def test_own_order_read_and_cross_user_denied(session, seeded) -> None:
    data = seeded
    tools = _order_tools(session)

    own = await tools.get_order_status(
        {"order_id": str(data["order"].id)}, context=_ctx(data["user_a"])
    )
    assert own.ok is True
    assert own.data["order_no"] == "IT-2026-0001"

    foreign = await tools.get_order_status(
        {"order_id": str(data["order"].id)}, context=_ctx(data["user_b"])
    )
    assert foreign.ok is False
    assert foreign.error_code == ErrorCode.ORDER_NOT_FOUND.value


async def test_shipment_returns_real_timeline(session, seeded) -> None:
    data = seeded
    tools = _order_tools(session)
    result = await tools.get_shipment(
        {"order_id": str(data["order"].id)}, context=_ctx(data["user_a"])
    )
    assert result.ok is True
    assert result.data["tracking_no_masked"] == "IT****0001"
    assert len(result.data["events"]) == 1


async def test_return_create_is_idempotent_with_one_row(session, seeded) -> None:
    data = seeded
    tools = _return_tools(session)
    ctx = _ctx(data["user_a"])

    check = await tools.check_return_eligibility(
        {
            "order_id": str(data["order"].id),
            "order_item_id": str(data["item"].id),
            "reason_code": "SIZE_OR_FIT",
        },
        context=ctx,
    )
    assert check.data["decision"] == "eligible"

    grant = ConfirmationGrant(
        operation="create_return_request",
        order_id=data["order"].id,
        order_item_id=data["item"].id,
        reason_code="SIZE_OR_FIT",
        expires_at=NOW + timedelta(minutes=10),
    )
    payload = {
        "order_id": str(data["order"].id),
        "order_item_id": str(data["item"].id),
        "reason_code": "SIZE_OR_FIT",
        "eligibility_token": check.data["eligibility_token"],
    }
    first = await tools.create_return_request(
        payload,
        context=_ctx(data["user_a"], confirmation=grant, idempotency_key="it-return-key-000000001"),
    )
    second = await tools.create_return_request(
        payload,
        context=_ctx(data["user_a"], confirmation=grant, idempotency_key="it-return-key-000000001"),
    )

    assert first.ok is True
    assert first.data["refund_status"] == "not_created"
    assert second.idempotent_replay is True
    assert second.tool_call_id == first.tool_call_id

    rows = (
        (
            await session.execute(
                sa.select(ReturnRequest).where(ReturnRequest.shop_id == data["shop"].id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert str(rows[0].status) == "submitted"

    calls = (
        (
            await session.execute(
                sa.select(ToolCall).where(
                    ToolCall.tool_name == "create_return_request",
                    ToolCall.shop_id == data["shop"].id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(calls) == 1

    idem = (
        (
            await session.execute(
                sa.select(IdempotencyRecord).where(IdempotencyRecord.shop_id == data["shop"].id)
            )
        )
        .scalars()
        .all()
    )
    assert len(idem) == 1


async def test_duplicate_return_with_new_key_is_blocked(session, seeded) -> None:
    data = seeded
    tools = _return_tools(session)
    grant = ConfirmationGrant(
        operation="create_return_request",
        order_id=data["order"].id,
        order_item_id=data["item"].id,
        reason_code="SIZE_OR_FIT",
        expires_at=NOW + timedelta(minutes=10),
    )
    check = await tools.check_return_eligibility(
        {
            "order_id": str(data["order"].id),
            "order_item_id": str(data["item"].id),
            "reason_code": "SIZE_OR_FIT",
        },
        context=_ctx(data["user_a"]),
    )
    await tools.create_return_request(
        {
            "order_id": str(data["order"].id),
            "order_item_id": str(data["item"].id),
            "reason_code": "SIZE_OR_FIT",
            "eligibility_token": check.data["eligibility_token"],
        },
        context=_ctx(data["user_a"], confirmation=grant, idempotency_key="it-return-key-000000002"),
    )
    second = await tools.create_return_request(
        {
            "order_id": str(data["order"].id),
            "order_item_id": str(data["item"].id),
            "reason_code": "SIZE_OR_FIT",
            "eligibility_token": check.data["eligibility_token"],
        },
        context=_ctx(data["user_a"], confirmation=grant, idempotency_key="it-return-key-000000003"),
    )
    assert second.error_code == ErrorCode.DUPLICATE_RETURN.value


async def test_completed_return_still_blocks_a_new_application(session, seeded) -> None:
    """已完成的退货申请同样阻断重复申请（§16.2.2「已退款」的数据契约等价语义）。

    数据契约没有订单级 ``refunded``（docs/04-data-contract.md §6.1），"已退款"在本项目里
    等价于 ``order_item.status=returned`` 或 ``return_request.status=completed``。仓库层的
    ``find_active_return`` 必须把 ``completed`` 也视为阻断记录，否则审批完成之后
    ``order_items.status`` 不会自动变成 ``returned``，消费者可以再提交一次同样的申请。
    """
    data = seeded
    completed = ReturnRequest(
        id=uuid4(),
        shop_id=data["shop"].id,
        user_id=data["user_a"].id,
        order_id=data["order"].id,
        order_item_id=data["item"].id,
        reason_code=ReturnReasonCode.SIZE_OR_FIT,
        status=ReturnStatus.COMPLETED,
        requested_at=NOW - timedelta(days=1),
        decided_at=NOW,
        decision_reason="已完成（合成）",
    )
    session.add(completed)
    await session.commit()

    blocking = await OrderRepository(session).find_active_return(
        shop_id=data["shop"].id, order_item_id=data["item"].id
    )
    assert blocking is not None, "已完成的退货申请必须被视为阻断记录"
    assert blocking.id == completed.id
    assert blocking.status is ReturnStatus.COMPLETED

    # 端到端：资格检查必须返回 DUPLICATE_RETURN，且不得签发资格令牌。
    check = await _return_tools(session).check_return_eligibility(
        {
            "order_id": str(data["order"].id),
            "order_item_id": str(data["item"].id),
            "reason_code": "SIZE_OR_FIT",
        },
        context=_ctx(data["user_a"]),
    )
    assert check.ok is True
    assert check.data["decision_code"] == "DUPLICATE_RETURN"
    assert check.data["can_create_return_request"] is False
    assert check.data["eligibility_token"] is None
    assert check.data["existing_return"]["status"] == "completed"


@pytest.mark.parametrize("status", [ReturnStatus.REJECTED, ReturnStatus.DRAFT], ids=str)
async def test_finished_refusal_or_draft_does_not_block_a_new_application(
    session, seeded, status
) -> None:
    """被拒或草稿不阻断：消费者可以在窗口内重新申请（不得过度拦截）。"""
    data = seeded
    session.add(
        ReturnRequest(
            id=uuid4(),
            shop_id=data["shop"].id,
            user_id=data["user_a"].id,
            order_id=data["order"].id,
            order_item_id=data["item"].id,
            reason_code=ReturnReasonCode.SIZE_OR_FIT,
            status=status,
            requested_at=NOW - timedelta(days=1),
        )
    )
    await session.commit()

    assert (
        await OrderRepository(session).find_active_return(
            shop_id=data["shop"].id, order_item_id=data["item"].id
        )
        is None
    )

    check = await _return_tools(session).check_return_eligibility(
        {
            "order_id": str(data["order"].id),
            "order_item_id": str(data["item"].id),
            "reason_code": "SIZE_OR_FIT",
        },
        context=_ctx(data["user_a"]),
    )
    assert check.data["decision_code"] == "RETURN_ELIGIBLE"
    assert check.data["eligibility_token"] is not None


async def test_handoff_creates_open_ticket_and_audit(session, seeded) -> None:
    data = seeded
    tools = _handoff_tools(session)
    result = await tools.create_handoff_ticket(
        {
            "conversation_id": str(data["conversation"].id),
            "reason_code": "LEGAL_OR_REGULATORY",
            "summary_redacted": "用户提及法律途径。",
        },
        context=_ctx(
            data["user_a"],
            conversation_id=data["conversation"].id,
            idempotency_key="it-handoff-key-0000001",
        ),
    )
    assert result.ok is True
    assert result.data["status"] == "open"
    assert result.data["risk_level"] == "critical"

    tickets = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(HandoffTicket)
            .where(HandoffTicket.shop_id == data["shop"].id)
        )
    ).scalar_one()
    assert tickets == 1

    events = (
        (
            await session.execute(
                sa.select(AuditEvent).where(
                    AuditEvent.action == "handoff_ticket.create",
                    AuditEvent.shop_id == data["shop"].id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
