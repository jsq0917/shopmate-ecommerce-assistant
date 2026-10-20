"""Ports the order/return tools depend on.

Every method takes ``shop_id`` and a user id, so a caller cannot forget the two filters
that separate tenants and owners. The real implementation lives in
``db/repositories/orders.py``; unit tests use an in-memory fake.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from shopmate_ecommerce_assistant.domain.orders.models import (
    ActiveReturnSnapshot,
    ConversationSnapshot,
    OrderItemSnapshot,
    OrderSnapshot,
    ShipmentSnapshot,
)


class OrderReader(Protocol):
    """Shop- and user-scoped order facts."""

    async def get_order(
        self,
        *,
        shop_id: UUID,
        user_id: UUID,
        order_id: UUID | None = None,
        order_no: str | None = None,
    ) -> OrderSnapshot | None:
        """Return the order only when it belongs to ``user_id`` inside ``shop_id``."""
        ...

    async def get_order_item(
        self, *, shop_id: UUID, order_id: UUID, order_item_id: UUID
    ) -> OrderItemSnapshot | None:
        """Return one line of that order, or ``None`` when it is not part of it."""
        ...

    async def list_order_items(
        self, *, shop_id: UUID, order_id: UUID
    ) -> tuple[OrderItemSnapshot, ...]:
        """Return every line of an order (already ownership-checked by the caller)."""
        ...

    async def get_shipment(self, *, shop_id: UUID, order_id: UUID) -> ShipmentSnapshot | None:
        """Return the newest shipment of the order, or ``None``."""
        ...

    async def find_active_return(
        self, *, shop_id: UUID, order_item_id: UUID
    ) -> ActiveReturnSnapshot | None:
        """Return the record that blocks a new application, if any.

        Blocking covers the open states (``submitted``/``under_review``/``approved``) and
        the finished state (``completed``); ``rejected``/``draft``/``cancelled`` do not
        block. Callers read the result as the ``has_active_return`` fact.
        """
        ...

    async def get_conversation(
        self, *, shop_id: UUID, conversation_id: UUID, user_id: UUID
    ) -> ConversationSnapshot | None:
        """Return the conversation only when it belongs to that user in that shop."""
        ...
