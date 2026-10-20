"""Unit tests for get_order_status and get_shipment against a fake reader."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from shopmate_ecommerce_assistant.core.errors import ErrorCode
from shopmate_ecommerce_assistant.db.models.enums import ShipmentStatus, UserRole
from shopmate_ecommerce_assistant.domain.orders.models import (
    ShipmentEventSnapshot,
    ShipmentSnapshot,
)
from shopmate_ecommerce_assistant.tools.context import ToolContext
from shopmate_ecommerce_assistant.tools.order_tools import OrderTools
from shopmate_ecommerce_assistant.tools.runtime import ToolRuntime
from tests.support.fakes import FakeOrderReader, InMemoryAudit, make_order

SHOP = uuid4()


def _ctx(role=UserRole.SHOPPER, *, user=None, effective_user_id=None, permissions=()):
    actor = user or uuid4()
    return ToolContext(
        shop_id=SHOP,
        actor_user_id=actor,
        role=role,
        request_id=uuid4(),
        trace_id=uuid4(),
        effective_user_id=effective_user_id,
        permissions=frozenset(permissions),
    )


def _tools(reader, *, audit):
    return OrderTools(reader, runtime=ToolRuntime(audit=audit))


async def test_get_order_status_returns_facts() -> None:
    order = make_order(order_no="SM-2026-00001")
    reader = FakeOrderReader(orders={order.id: order})
    audit = InMemoryAudit()
    tools = _tools(reader, audit=audit)
    ctx = _ctx(user=order.user_id)

    result = await tools.get_order_status({"order_id": str(order.id)}, context=ctx)

    assert result.ok is True
    assert result.data["order_no"] == "SM-2026-00001"
    assert result.data["status"] == "delivered"
    assert result.data["total_cents"] == 29_900
    assert {e["status"] for e in result.data["timeline"]} >= {"created", "delivered"}
    assert result.as_of == order.updated_at
    assert audit.tool_calls and audit.tool_calls[-1].tool_name == "get_order_status"


async def test_get_order_status_by_order_no() -> None:
    order = make_order(order_no="SM-2026-0042")
    reader = FakeOrderReader(orders={order.id: order})
    tools = _tools(reader, audit=InMemoryAudit())
    ctx = _ctx(user=order.user_id)

    result = await tools.get_order_status({"order_no": "SM-2026-0042"}, context=ctx)

    assert result.ok is True
    assert result.data["order_no"] == "SM-2026-0042"


async def test_missing_order_is_safe_not_found() -> None:
    tools = _tools(FakeOrderReader(), audit=InMemoryAudit())
    result = await tools.get_order_status({"order_id": str(uuid4())}, context=_ctx())
    assert result.ok is False
    assert result.error_code == ErrorCode.ORDER_NOT_FOUND.value
    assert "SQL" not in result.user_message and "Traceback" not in result.user_message


async def test_other_users_order_is_same_not_found() -> None:
    order = make_order()
    tools = _tools(FakeOrderReader(orders={order.id: order}), audit=InMemoryAudit())
    result = await tools.get_order_status({"order_id": str(order.id)}, context=_ctx())
    assert result.ok is False
    assert result.error_code == ErrorCode.ORDER_NOT_FOUND.value


async def test_ambiguous_reference_is_validation_error() -> None:
    tools = _tools(FakeOrderReader(), audit=InMemoryAudit())
    result = await tools.get_order_status(
        {"order_id": str(uuid4()), "order_no": "X"}, context=_ctx()
    )
    assert result.error_code == ErrorCode.VALIDATION_ERROR.value


async def test_support_without_scope_is_forbidden() -> None:
    order = make_order()
    tools = _tools(FakeOrderReader(orders={order.id: order}), audit=InMemoryAudit())
    ctx = _ctx(role=UserRole.SUPPORT, effective_user_id=order.user_id)
    result = await tools.get_order_status({"order_id": str(order.id)}, context=ctx)
    assert result.error_code == ErrorCode.FORBIDDEN.value


async def test_support_with_scope_can_read() -> None:
    order = make_order()
    tools = _tools(FakeOrderReader(orders={order.id: order}), audit=InMemoryAudit())
    ctx = _ctx(
        role=UserRole.SUPPORT,
        user=uuid4(),
        effective_user_id=order.user_id,
        permissions=("support:conversation:read",),
    )
    result = await tools.get_order_status({"order_id": str(order.id)}, context=ctx)
    assert result.ok is True


async def test_shopper_cannot_impersonate_another_user() -> None:
    order = make_order()
    tools = _tools(FakeOrderReader(orders={order.id: order}), audit=InMemoryAudit())
    ctx = _ctx(user=uuid4(), effective_user_id=order.user_id)
    result = await tools.get_order_status({"order_id": str(order.id)}, context=ctx)
    assert result.error_code == ErrorCode.FORBIDDEN.value


async def test_get_shipment_returns_timeline() -> None:
    order = make_order()
    shipment = ShipmentSnapshot(
        id=uuid4(),
        order_id=order.id,
        carrier="顺捷速运（合成）",
        tracking_no_masked="SF1000****0001",
        status=ShipmentStatus.IN_TRANSIT,
        shipped_at=datetime(2026, 10, 11, 0, 0),
        estimated_delivery_at=datetime(2026, 10, 14, 0, 0),
        delivered_at=None,
        updated_at=datetime(2026, 10, 12, 0, 0),
        is_synthetic=True,
        events=(
            ShipmentEventSnapshot(
                status=ShipmentStatus.PICKED_UP,
                description="快件已由仓库揽收",
                occurred_at=datetime(2026, 10, 11, 1, 0),
            ),
        ),
    )
    reader = FakeOrderReader(orders={order.id: order}, shipments={order.id: shipment})
    tools = _tools(reader, audit=InMemoryAudit())
    result = await tools.get_shipment({"order_id": str(order.id)}, context=_ctx(user=order.user_id))

    assert result.ok is True
    assert result.data["tracking_no_masked"] == "SF1000****0001"
    assert len(result.data["events"]) == 1


async def test_get_shipment_without_shipment_is_not_found() -> None:
    order = make_order()
    reader = FakeOrderReader(orders={order.id: order})
    tools = _tools(reader, audit=InMemoryAudit())
    result = await tools.get_shipment({"order_id": str(order.id)}, context=_ctx(user=order.user_id))
    assert result.error_code == ErrorCode.SHIPMENT_NOT_FOUND.value


async def test_extra_identity_field_is_rejected() -> None:
    order = make_order()
    reader = FakeOrderReader(orders={order.id: order})
    tools = _tools(reader, audit=InMemoryAudit())
    result = await tools.get_order_status(
        {"order_id": str(order.id), "shop_id": str(uuid4())}, context=_ctx(user=order.user_id)
    )
    assert result.error_code == ErrorCode.VALIDATION_ERROR.value
