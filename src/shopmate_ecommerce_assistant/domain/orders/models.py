"""Read-only order, order-item and shipment snapshots.

The repository fills these dataclasses from PostgreSQL; the tools render them. No ORM
object leaves the repository, which is what keeps the rule engine unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from shopmate_ecommerce_assistant.db.models.enums import (
    OrderItemStatus,
    OrderStatus,
    ReturnStatus,
    ShipmentStatus,
)


@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    """Order header facts. ``updated_at`` is the ``as_of`` of the status."""

    id: UUID
    user_id: UUID
    order_no: str
    status: OrderStatus
    total_cents: int
    currency: str
    placed_at: datetime
    delivered_at: datetime | None
    cancelled_at: datetime | None
    updated_at: datetime
    is_synthetic: bool


@dataclass(frozen=True, slots=True)
class OrderItemSnapshot:
    """One order line with the immutable snapshots the return rules rely on."""

    id: UUID
    order_id: UUID
    sku: str
    title: str
    category: str
    is_returnable: bool
    quantity: int
    unit_price_cents: int
    line_total_cents: int
    status: OrderItemStatus
    delivered_at: datetime | None


@dataclass(frozen=True, slots=True)
class ShipmentEventSnapshot:
    """One immutable logistics node."""

    status: ShipmentStatus
    description: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ShipmentSnapshot:
    """Shipment header plus its ordered timeline."""

    id: UUID
    order_id: UUID
    carrier: str
    tracking_no_masked: str
    status: ShipmentStatus
    shipped_at: datetime | None
    estimated_delivery_at: datetime | None
    delivered_at: datetime | None
    updated_at: datetime
    is_synthetic: bool
    events: tuple[ShipmentEventSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class ActiveReturnSnapshot:
    """An existing application that still blocks a new one."""

    id: UUID
    status: ReturnStatus
    reason_code: str
    requested_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationSnapshot:
    """Minimal conversation ownership fact."""

    id: UUID
    user_id: UUID
