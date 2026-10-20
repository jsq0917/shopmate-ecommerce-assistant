"""In-memory fakes for the order/return/handoff tool tests.

They implement the ports (``OrderReader``, ``IdempotencyStore``, ``ReturnWriter``,
``HandoffWriter``, ``AuditSink``) so the tools can be exercised without PostgreSQL while the
database-backed implementations are covered separately by the integration tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError

from shopmate_ecommerce_assistant.db.models.enums import (
    OrderItemStatus,
    OrderStatus,
)
from shopmate_ecommerce_assistant.domain.audit.models import AuditEventRecord, ToolCallRecord
from shopmate_ecommerce_assistant.domain.handoff.ports import HandoffTicketRecord
from shopmate_ecommerce_assistant.domain.idempotency import (
    ClaimKind,
    ClaimResult,
    IdempotencyScope,
    IdempotencyState,
)
from shopmate_ecommerce_assistant.domain.orders.models import (
    ActiveReturnSnapshot,
    ConversationSnapshot,
    OrderItemSnapshot,
    OrderSnapshot,
    ShipmentSnapshot,
)
from shopmate_ecommerce_assistant.domain.returns.ports import (
    ReturnConflictError,
    ReturnRequestRecord,
)


@dataclass
class FakeOrderReader:
    """Store order facts and answer ownership-scoped lookups."""

    orders: dict[UUID, OrderSnapshot] = field(default_factory=dict)
    items: dict[UUID, OrderItemSnapshot] = field(default_factory=dict)
    shipments: dict[UUID, ShipmentSnapshot] = field(default_factory=dict)
    active_returns: dict[UUID, ActiveReturnSnapshot] = field(default_factory=dict)
    conversations: dict[UUID, ConversationSnapshot] = field(default_factory=dict)

    async def get_order(
        self,
        *,
        shop_id,
        user_id,
        order_id=None,
        order_no=None,
    ):
        if order_id is not None:
            order = self.orders.get(order_id)
        else:
            order = next((o for o in self.orders.values() if o.order_no == order_no), None)
        if order is None or order.user_id != user_id:
            return None
        return order

    async def get_order_item(self, *, shop_id, order_id, order_item_id):
        item = self.items.get(order_item_id)
        if item is None or item.order_id != order_id:
            return None
        return item

    async def list_order_items(self, *, shop_id, order_id):
        return tuple(i for i in self.items.values() if i.order_id == order_id)

    async def get_shipment(self, *, shop_id, order_id):
        return self.shipments.get(order_id)

    async def find_active_return(self, *, shop_id, order_item_id):
        return self.active_returns.get(order_item_id)

    async def get_conversation(self, *, shop_id, conversation_id, user_id):
        conv = self.conversations.get(conversation_id)
        if conv is None or conv.user_id != user_id:
            return None
        return conv


@dataclass
class FakeIdempotencyStore:
    """Deterministic idempotency store that also records calls for assertions."""

    records: dict[tuple[UUID, str], IdempotencyState] = field(default_factory=dict)
    claimed: list[IdempotencyScope] = field(default_factory=list)
    succeeded: list[IdempotencyScope] = field(default_factory=list)
    failed: list[IdempotencyScope] = field(default_factory=list)

    def _key(self, scope: IdempotencyScope) -> tuple[UUID, str]:
        return (scope.actor_user_id, scope.key)

    async def claim(self, scope: IdempotencyScope, *, request_hash: bytes) -> ClaimResult:
        key = self._key(scope)
        existing = self.records.get(key)
        if existing is None:
            self.records[key] = IdempotencyState(status="processing", request_hash=request_hash)
            self.claimed.append(scope)
            return ClaimResult(ClaimKind.CLAIMED)
        if existing.request_hash != request_hash:
            return ClaimResult(ClaimKind.CONFLICT, existing)
        if existing.status == "succeeded":
            return ClaimResult(ClaimKind.REPLAY, existing)
        if existing.status == "failed":
            return ClaimResult(ClaimKind.FAILED, existing)
        return ClaimResult(ClaimKind.IN_PROGRESS, existing)

    async def mark_succeeded(self, scope, *, resource_type, resource_id, response):
        key = self._key(scope)
        state = self.records.get(key) or IdempotencyState(status="processing", request_hash=b"")
        self.records[key] = IdempotencyState(
            status="succeeded",
            request_hash=state.request_hash,
            resource_type=resource_type,
            resource_id=resource_id,
            response=response,
        )
        self.succeeded.append(scope)

    async def mark_failed(self, scope, *, error_code: str):
        key = self._key(scope)
        state = self.records.get(key) or IdempotencyState(status="processing", request_hash=b"")
        self.records[key] = IdempotencyState(
            status="failed", request_hash=state.request_hash, error_code=error_code
        )
        self.failed.append(scope)

    async def release(self, scope):
        """Delete the key only while it is still ``processing`` (mirrors the repository)."""
        key = self._key(scope)
        existing = self.records.get(key)
        if existing is not None and existing.status == "processing":
            del self.records[key]


@dataclass
class FakeReturnWriter:
    """Records a submitted application; can raise :class:`ReturnConflictError` on demand."""

    created: list[ReturnRequestRecord] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    audit_events: list[AuditEventRecord] = field(default_factory=list)
    conflict: bool = False
    store: FakeIdempotencyStore | None = None

    async def create_submitted(self, **kwargs) -> ReturnRequestRecord:
        if self.conflict:
            raise ReturnConflictError("duplicate")
        record = ReturnRequestRecord(
            id=kwargs["return_request_id"],
            order_id=kwargs["order_id"],
            order_item_id=kwargs["order_item_id"],
            reason_code=kwargs["reason_code"],
            status="submitted",
            submitted_at=datetime.now(),
            required_materials=kwargs["required_materials"],
        )
        self.created.append(record)
        self.tool_calls.append(kwargs["tool_call"])
        self.audit_events.append(kwargs["audit"])
        if self.store is not None:
            await self.store.mark_succeeded(
                kwargs["scope"],
                resource_type="return_request",
                resource_id=record.id,
                response=kwargs["response"],
            )
        return record


@dataclass
class FakeHandoffWriter:
    """Records an open ticket; can simulate transient SQLAlchemy failures on demand."""

    created: list[HandoffTicketRecord] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    audit_events: list[AuditEventRecord] = field(default_factory=list)
    store: FakeIdempotencyStore | None = None
    fail_attempts: int = 0
    _calls: int = field(default=0, init=False)

    async def create_open(self, **kwargs) -> HandoffTicketRecord:
        if self._calls < self.fail_attempts:
            self._calls += 1
            raise SQLAlchemyError("simulated transient outage")
        self._calls += 1
        record = HandoffTicketRecord(
            id=kwargs["ticket_id"],
            status="open",
            risk_level=kwargs["risk_level"],
            priority=kwargs["priority"],
            primary_reason_code=kwargs["primary_reason_code"],
            reason_codes=kwargs["reason_codes"],
            created_at=datetime.now(),
        )
        self.created.append(record)
        self.tool_calls.append(kwargs["tool_call"])
        self.audit_events.append(kwargs["audit"])
        if self.store is not None:
            await self.store.mark_succeeded(
                kwargs["scope"],
                resource_type="handoff_ticket",
                resource_id=record.id,
                response=kwargs["response"],
            )
        return record


@dataclass
class InMemoryAudit:
    """Collects audit records for assertions."""

    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    events: list[AuditEventRecord] = field(default_factory=list)

    async def record_tool_call(self, record: ToolCallRecord) -> None:
        self.tool_calls.append(record)

    async def record_event(self, event: AuditEventRecord) -> None:
        self.events.append(event)


def make_order(**overrides: Any) -> OrderSnapshot:
    base = dict(
        id=uuid4(),
        user_id=uuid4(),
        order_no="SM-2026-00001",
        status=OrderStatus.DELIVERED,
        total_cents=29900,
        currency="CNY",
        placed_at=datetime(2026, 10, 10, 0, 0),
        delivered_at=datetime(2026, 10, 12, 0, 0),
        cancelled_at=None,
        updated_at=datetime(2026, 10, 12, 0, 0),
        is_synthetic=True,
    )
    base.update(overrides)
    return OrderSnapshot(**base)


def make_item(order_id: UUID, **overrides: Any) -> OrderItemSnapshot:
    base = dict(
        id=uuid4(),
        order_id=order_id,
        sku="SM-X-01",
        title="示例商品",
        category="耳机",
        is_returnable=True,
        quantity=1,
        unit_price_cents=29900,
        line_total_cents=29900,
        status=OrderItemStatus.ACTIVE,
        delivered_at=datetime(2026, 10, 12, 0, 0),
    )
    base.update(overrides)
    return OrderItemSnapshot(**base)
