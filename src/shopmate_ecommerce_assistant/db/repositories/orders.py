"""Parameterized, shop- and user-scoped order queries.

Every statement filters on ``shop_id`` *and* a user id. The order lookup applies both, so
"not found" and "someone else's order" are indistinguishable by construction; the shipment
query is only reached after the order has been proven to belong to the subject.
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.db.models import (
    Conversation,
    Order,
    OrderItem,
    ReturnRequest,
    ReturnStatus,
    Shipment,
    ShipmentEvent,
)
from shopmate_ecommerce_assistant.db.models.enums import (
    OrderItemStatus,
    OrderStatus,
    ShipmentStatus,
)
from shopmate_ecommerce_assistant.domain.orders.models import (
    ActiveReturnSnapshot,
    ConversationSnapshot,
    OrderItemSnapshot,
    OrderSnapshot,
    ShipmentEventSnapshot,
    ShipmentSnapshot,
)

_ACTIVE_RETURN_STATUSES = (
    ReturnStatus.SUBMITTED,
    ReturnStatus.UNDER_REVIEW,
    ReturnStatus.APPROVED,
)

#: A *finished* return must also block a second application. Once a review reaches
#: ``completed`` the goods are back, and nothing in this codebase flips
#: ``order_items.status`` to ``returned``, so without this the customer could legally file
#: the same request again. ``rejected`` / ``draft`` never block: after a refusal the shopper
#: may re-apply (with better evidence) inside the window.
_CLOSED_RETURN_STATUSES = (ReturnStatus.COMPLETED,)

_BLOCKING_RETURN_STATUSES = (*_ACTIVE_RETURN_STATUSES, *_CLOSED_RETURN_STATUSES)


class OrderRepository:
    """SQLAlchemy implementation of :class:`OrderReader`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_order(
        self,
        *,
        shop_id: UUID,
        user_id: UUID,
        order_id: UUID | None = None,
        order_no: str | None = None,
    ) -> OrderSnapshot | None:
        """Return the order only when it belongs to ``user_id`` inside ``shop_id``."""
        if (order_id is None) == (order_no is None):
            return None
        stmt = sa.select(Order).where(Order.shop_id == shop_id, Order.user_id == user_id)
        stmt = (
            stmt.where(Order.id == order_id) if order_id else stmt.where(Order.order_no == order_no)
        )
        order = (await self._session.execute(stmt.limit(1))).scalar_one_or_none()
        return None if order is None else _order_snapshot(order)

    async def get_order_item(
        self, *, shop_id: UUID, order_id: UUID, order_item_id: UUID
    ) -> OrderItemSnapshot | None:
        """Return one line, scoped to the order and the shop."""
        stmt = sa.select(OrderItem).where(
            OrderItem.shop_id == shop_id,
            OrderItem.order_id == order_id,
            OrderItem.id == order_item_id,
        )
        item = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if item is None else _item_snapshot(item)

    async def list_orders(
        self,
        *,
        shop_id: UUID,
        user_id: UUID,
        status: OrderStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[OrderSnapshot, ...]:
        """Return the user's orders, newest first, optionally filtered by status."""
        stmt = (
            sa.select(Order)
            .where(Order.shop_id == shop_id, Order.user_id == user_id)
            .order_by(Order.placed_at.desc(), Order.id)
            .offset(offset)
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(Order.status == status)
        rows = (await self._session.execute(stmt)).scalars().all()
        return tuple(_order_snapshot(order) for order in rows)

    async def list_order_items_with_orders(
        self, *, shop_id: UUID, user_id: UUID, order_ids: tuple[UUID, ...]
    ) -> dict[UUID, tuple[OrderItemSnapshot, ...]]:
        """Return order items grouped by order id, only for the user's own orders."""
        if not order_ids:
            return {}
        stmt = (
            sa.select(OrderItem)
            .join(
                Order,
                sa.and_(
                    Order.id == OrderItem.order_id,
                    Order.shop_id == OrderItem.shop_id,
                ),
            )
            .where(
                OrderItem.shop_id == shop_id,
                Order.user_id == user_id,
                OrderItem.order_id.in_(order_ids),
            )
            .order_by(OrderItem.created_at, OrderItem.id)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        grouped: dict[UUID, list[OrderItemSnapshot]] = {}
        for item in rows:
            grouped.setdefault(item.order_id, []).append(_item_snapshot(item))
        return {key: tuple(value) for key, value in grouped.items()}

    async def list_order_items(
        self, *, shop_id: UUID, order_id: UUID
    ) -> tuple[OrderItemSnapshot, ...]:
        """Return every line of an order in insertion order."""
        stmt = (
            sa.select(OrderItem)
            .where(OrderItem.shop_id == shop_id, OrderItem.order_id == order_id)
            .order_by(OrderItem.created_at, OrderItem.id)
        )
        items = (await self._session.execute(stmt)).scalars().all()
        return tuple(_item_snapshot(item) for item in items)

    async def get_shipment(self, *, shop_id: UUID, order_id: UUID) -> ShipmentSnapshot | None:
        """Return the newest shipment of the order plus its node timeline."""
        stmt = (
            sa.select(Shipment)
            .where(Shipment.shop_id == shop_id, Shipment.order_id == order_id)
            .order_by(Shipment.updated_at.desc(), Shipment.id)
            .limit(1)
        )
        shipment = (await self._session.execute(stmt)).scalar_one_or_none()
        if shipment is None:
            return None

        event_stmt = (
            sa.select(ShipmentEvent)
            .where(
                ShipmentEvent.shop_id == shop_id,
                ShipmentEvent.shipment_id == shipment.id,
            )
            .order_by(ShipmentEvent.sequence_no)
        )
        events = (await self._session.execute(event_stmt)).scalars().all()
        return _shipment_snapshot(shipment, events)

    async def find_active_return(
        self, *, shop_id: UUID, order_item_id: UUID
    ) -> ActiveReturnSnapshot | None:
        """Return the record that *blocks* a new application, regardless of reason code.

        Blocking means an open application (``submitted``/``under_review``/``approved``)
        **or** a finished one (``completed``): both describe an item that is already on its
        way back or already back. ``rejected``/``draft``/``cancelled`` do not block.
        Callers therefore use ``is not None`` as ``has_active_return``.
        """
        stmt = (
            sa.select(ReturnRequest)
            .where(
                ReturnRequest.shop_id == shop_id,
                ReturnRequest.order_item_id == order_item_id,
                ReturnRequest.status.in_(_BLOCKING_RETURN_STATUSES),
            )
            .order_by(ReturnRequest.created_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return ActiveReturnSnapshot(
            id=row.id,
            status=ReturnStatus(str(row.status)),
            reason_code=str(row.reason_code),
            requested_at=row.requested_at,
        )

    async def get_conversation(
        self, *, shop_id: UUID, conversation_id: UUID, user_id: UUID
    ) -> ConversationSnapshot | None:
        """Return the live conversation only when it belongs to that user."""
        stmt = sa.select(Conversation).where(
            Conversation.shop_id == shop_id,
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if row is None else ConversationSnapshot(id=row.id, user_id=row.user_id)


def _order_snapshot(order: Order) -> OrderSnapshot:
    return OrderSnapshot(
        id=order.id,
        user_id=order.user_id,
        order_no=order.order_no,
        status=OrderStatus(str(order.status)),
        total_cents=order.total_cents,
        currency=order.currency,
        placed_at=order.placed_at,
        delivered_at=order.delivered_at,
        cancelled_at=order.cancelled_at,
        updated_at=order.updated_at,
        is_synthetic=order.is_synthetic,
    )


def _item_snapshot(item: OrderItem) -> OrderItemSnapshot:
    return OrderItemSnapshot(
        id=item.id,
        order_id=item.order_id,
        sku=item.sku_snapshot,
        title=item.title_snapshot,
        category=item.category_snapshot,
        is_returnable=item.is_returnable_snapshot,
        quantity=item.quantity,
        unit_price_cents=item.unit_price_cents,
        line_total_cents=item.line_total_cents,
        status=OrderItemStatus(str(item.status)),
        delivered_at=item.delivered_at,
    )


def _shipment_snapshot(shipment: Shipment, events: list[ShipmentEvent]) -> ShipmentSnapshot:
    return ShipmentSnapshot(
        id=shipment.id,
        order_id=shipment.order_id,
        carrier=shipment.carrier,
        tracking_no_masked=shipment.tracking_no_masked,
        status=ShipmentStatus(str(shipment.status)),
        shipped_at=shipment.shipped_at,
        estimated_delivery_at=shipment.estimated_delivery_at,
        delivered_at=shipment.delivered_at,
        updated_at=shipment.updated_at,
        is_synthetic=shipment.is_synthetic,
        events=tuple(
            ShipmentEventSnapshot(
                status=ShipmentStatus(str(event.status)),
                description=event.description,
                occurred_at=event.occurred_at,
            )
            for event in events
        ),
    )


__all__ = ["OrderRepository"]
