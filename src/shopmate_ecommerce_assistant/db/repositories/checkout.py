"""Self-service checkout and refund persistence.

This module owns the *shopper-facing* write path for orders and refunds. It deliberately
mirrors the safety rules of the assistant tools:

* every statement is scoped by ``shop_id`` **and** ``user_id``, so "someone else's order"
  and "no such order" are indistinguishable;
* stock is only decremented on payment, inside one transaction, under a row lock, and only
  when the requested quantity is actually available (no oversell, no negative stock);
* cancelling a paid order restores exactly the quantity it took;
* a refund is created ``requested`` — approval is a human support action, money never moves
  and ``orders.total_cents`` is immutable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.db.models import (
    Inventory,
    Order,
    OrderItem,
    Product,
    ProductVariant,
    RefundRequest,
)
from shopmate_ecommerce_assistant.db.models.enums import (
    OrderItemStatus,
    OrderStatus,
    RefundStatus,
    ReturnReasonCode,
)
from shopmate_ecommerce_assistant.domain.returns.rules import is_category_returnable

MAX_ORDER_LINES = 20
MAX_LINE_QUANTITY = 99

#: Order states in which a shopper may still apply for a refund.
_REFUNDABLE_STATUSES = frozenset(
    {
        OrderStatus.PAID,
        OrderStatus.PROCESSING,
        OrderStatus.SHIPPED,
        OrderStatus.DELIVERED,
        OrderStatus.COMPLETED,
    }
)

_OPEN_REFUND_STATUSES = (RefundStatus.REQUESTED, RefundStatus.APPROVED)

_ORDER_NOT_FOUND = ToolError(ErrorCode.ORDER_NOT_FOUND, "未找到可由当前账号访问的订单。")


@dataclass(frozen=True, slots=True)
class CartLine:
    """One requested line: a variant and how many of it."""

    variant_id: UUID
    quantity: int


@dataclass(frozen=True, slots=True)
class OrderLineRow:
    """Detached view of one order line."""

    id: UUID
    variant_id: UUID | None
    sku: str
    title: str
    quantity: int
    unit_price_cents: int
    line_total_cents: int
    status: str
    is_returnable: bool


@dataclass(frozen=True, slots=True)
class OrderRow:
    """Detached view of an order plus its lines."""

    id: UUID
    order_no: str
    status: str
    total_cents: int
    currency: str
    placed_at: datetime
    paid_at: datetime | None
    delivered_at: datetime | None
    cancelled_at: datetime | None
    updated_at: datetime
    is_synthetic: bool
    lines: tuple[OrderLineRow, ...]


@dataclass(frozen=True, slots=True)
class RefundRow:
    """Detached view of a refund application."""

    id: UUID
    refund_no: str
    order_id: UUID
    order_no: str
    order_item_id: UUID | None
    scope: str
    status: str
    reason_code: str
    amount_cents: int
    note: str | None
    review_note: str | None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None


class CheckoutRepository:
    """Order and refund writes, always shop- and user-scoped."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- orders ------------------------------------------------------------
    async def create_order(
        self,
        *,
        shop_id: UUID,
        user_id: UUID,
        lines: list[CartLine],
        shipping_address_masked: str | None = None,
    ) -> OrderRow:
        """Create a ``created`` order from sellable variants; stock is untouched here."""
        if not lines:
            raise ToolError(ErrorCode.VALIDATION_ERROR, "请至少选择一件商品。")
        if len(lines) > MAX_ORDER_LINES:
            raise ToolError(ErrorCode.VALIDATION_ERROR, "单笔订单最多 20 个商品。")
        for line in lines:
            if line.quantity < 1 or line.quantity > MAX_LINE_QUANTITY:
                raise ToolError(ErrorCode.VALIDATION_ERROR, "商品数量必须在 1-99 之间。")

        merged: dict[UUID, int] = {}
        for line in lines:
            merged[line.variant_id] = merged.get(line.variant_id, 0) + line.quantity

        variant_ids = list(merged)
        stmt = (
            sa.select(ProductVariant, Product)
            .join(
                Product,
                sa.and_(
                    Product.id == ProductVariant.product_id,
                    Product.shop_id == ProductVariant.shop_id,
                ),
            )
            .where(
                ProductVariant.shop_id == shop_id,
                ProductVariant.id.in_(variant_ids),
                ProductVariant.status == "active",
                Product.status == "active",
            )
        )
        rows = (await self._session.execute(stmt)).all()
        found = {variant.id: (variant, product) for variant, product in rows}
        missing = [str(variant_id) for variant_id in variant_ids if variant_id not in found]
        if missing:
            raise ToolError(
                ErrorCode.VARIANT_NOT_FOUND,
                "有商品规格已下架或不属于当前店铺，请刷新后重新选择。",
            )

        order_id = uuid4()
        order_no = await self._next_number("SM-2026", Order, Order.order_no)
        now = datetime.now(UTC)
        total_cents = 0
        item_rows: list[OrderItem] = []
        for variant_id, quantity in merged.items():
            variant, product = found[variant_id]
            available = await self._available_qty(shop_id=shop_id, variant_id=variant_id)
            if available < quantity:
                raise ToolError(
                    ErrorCode.OUT_OF_STOCK,
                    f"「{product.title}」库存不足，当前仅剩 {available} 件。",
                )
            line_total = int(variant.price_cents) * quantity
            total_cents += line_total
            item_rows.append(
                OrderItem(
                    id=uuid4(),
                    shop_id=shop_id,
                    order_id=order_id,
                    variant_id=variant.id,
                    sku_snapshot=variant.sku,
                    title_snapshot=variant.title,
                    category_snapshot=product.category,
                    is_returnable_snapshot=is_category_returnable(product.category),
                    quantity=quantity,
                    unit_price_cents=int(variant.price_cents),
                    line_total_cents=line_total,
                    status=OrderItemStatus.ACTIVE,
                )
            )

        order = Order(
            id=order_id,
            shop_id=shop_id,
            user_id=user_id,
            order_no=order_no,
            status=OrderStatus.CREATED,
            total_cents=total_cents,
            currency="CNY",
            placed_at=now,
            shipping_address_masked=shipping_address_masked,
            source_system="storefront",
            is_synthetic=True,
        )
        self._session.add(order)
        self._session.add_all(item_rows)
        await self._session.commit()
        return await self.get_order(shop_id=shop_id, user_id=user_id, order_id=order_id)

    async def get_order(self, *, shop_id: UUID, user_id: UUID, order_id: UUID) -> OrderRow:
        """Return one order (with lines) that belongs to the caller."""
        stmt = sa.select(Order).where(
            Order.shop_id == shop_id, Order.user_id == user_id, Order.id == order_id
        )
        order = (await self._session.execute(stmt)).scalar_one_or_none()
        if order is None:
            raise _ORDER_NOT_FOUND
        return await self._row(order)

    async def pay_order(self, *, shop_id: UUID, user_id: UUID, order_id: UUID) -> OrderRow:
        """Simulate payment: reserve stock, then move ``created`` to ``paid``."""
        order = await self._locked_order(shop_id=shop_id, user_id=user_id, order_id=order_id)
        if OrderStatus(str(order.status)) is not OrderStatus.CREATED:
            raise ToolError(
                ErrorCode.INVALID_STATE,
                f"订单当前状态为 {order.status}，不能重复支付。",
            )
        items = await self._items(shop_id=shop_id, order_id=order_id)
        for item in items:
            if item.variant_id is None:
                continue
            await self._take_stock(
                shop_id=shop_id,
                variant_id=item.variant_id,
                quantity=item.quantity,
                title=item.title_snapshot,
            )
        order.status = OrderStatus.PAID
        order.paid_at = datetime.now(UTC)
        await self._session.commit()
        return await self.get_order(shop_id=shop_id, user_id=user_id, order_id=order_id)

    async def cancel_order(self, *, shop_id: UUID, user_id: UUID, order_id: UUID) -> OrderRow:
        """Cancel an unpaid or paid order; a paid one returns its stock."""
        order = await self._locked_order(shop_id=shop_id, user_id=user_id, order_id=order_id)
        status = OrderStatus(str(order.status))
        if status not in {OrderStatus.CREATED, OrderStatus.PAID, OrderStatus.PROCESSING}:
            raise ToolError(
                ErrorCode.INVALID_STATE,
                "订单已发货或已完成，不能直接取消；如需退款请在订单详情申请退款或退货。",
            )
        if status is not OrderStatus.CREATED:
            for item in await self._items(shop_id=shop_id, order_id=order_id):
                if item.variant_id is None:
                    continue
                await self._restore_stock(
                    shop_id=shop_id, variant_id=item.variant_id, quantity=item.quantity
                )
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = datetime.now(UTC)
        items = await self._items(shop_id=shop_id, order_id=order_id)
        for item in items:
            item.status = OrderItemStatus.CANCELLED
        await self._session.commit()
        return await self.get_order(shop_id=shop_id, user_id=user_id, order_id=order_id)

    # -- refunds -----------------------------------------------------------
    async def create_refund(
        self,
        *,
        shop_id: UUID,
        user_id: UUID,
        order_id: UUID,
        reason_code: ReturnReasonCode,
        order_item_id: UUID | None = None,
        note: str | None = None,
    ) -> RefundRow:
        """Create a ``requested`` refund for the whole order or one line."""
        order = await self._locked_order(shop_id=shop_id, user_id=user_id, order_id=order_id)
        status = OrderStatus(str(order.status))
        if status not in _REFUNDABLE_STATUSES:
            raise ToolError(
                ErrorCode.INVALID_STATE,
                "该订单当前状态不支持申请退款（未支付或已取消）。",
            )

        existing = (
            await self._session.execute(
                sa.select(sa.func.count())
                .select_from(RefundRequest)
                .where(
                    RefundRequest.shop_id == shop_id,
                    RefundRequest.order_id == order_id,
                    RefundRequest.status.in_([item.value for item in _OPEN_REFUND_STATUSES]),
                )
            )
        ).scalar()
        if existing:
            raise ToolError(
                ErrorCode.DUPLICATE_RETURN, "该订单已有处理中的退款申请，请勿重复提交。"
            )

        items = await self._items(shop_id=shop_id, order_id=order_id)
        amount_cents = int(order.total_cents)
        scope = "order"
        if order_item_id is not None:
            target = next((item for item in items if item.id == order_item_id), None)
            if target is None:
                raise ToolError(ErrorCode.VALIDATION_ERROR, "该商品不在所选订单中。")
            amount_cents = int(target.line_total_cents)
            scope = "item"

        refund_no = await self._next_number("RF-2026", RefundRequest, RefundRequest.refund_no)
        row = RefundRequest(
            id=uuid4(),
            shop_id=shop_id,
            user_id=user_id,
            order_id=order_id,
            order_item_id=order_item_id,
            refund_no=refund_no,
            scope=scope,
            status=RefundStatus.REQUESTED,
            reason_code=reason_code,
            amount_cents=amount_cents,
            note=(note or None),
            is_synthetic=True,
        )
        self._session.add(row)
        await self._session.commit()
        return await self._refund_row(row.id)

    async def list_refunds(
        self, *, shop_id: UUID, user_id: UUID, order_id: UUID | None = None, limit: int = 20
    ) -> tuple[RefundRow, ...]:
        """Return the caller's refund applications, newest first."""
        stmt = (
            sa.select(RefundRequest, Order.order_no)
            .join(
                Order,
                sa.and_(Order.id == RefundRequest.order_id, Order.shop_id == RefundRequest.shop_id),
            )
            .where(RefundRequest.shop_id == shop_id, RefundRequest.user_id == user_id)
            .order_by(RefundRequest.created_at.desc())
            .limit(limit)
        )
        if order_id is not None:
            stmt = stmt.where(RefundRequest.order_id == order_id)
        rows = (await self._session.execute(stmt)).all()
        return tuple(self._refund_from(row[0], row[1]) for row in rows)

    async def list_shop_refunds(
        self, *, shop_id: UUID, status: str | None = None, limit: int = 50
    ) -> tuple[RefundRow, ...]:
        """Support workbench queue: every refund of the shop, oldest first."""
        stmt = (
            sa.select(RefundRequest, Order.order_no)
            .join(
                Order,
                sa.and_(Order.id == RefundRequest.order_id, Order.shop_id == RefundRequest.shop_id),
            )
            .where(RefundRequest.shop_id == shop_id)
            .order_by(RefundRequest.created_at.asc())
            .limit(limit)
        )
        if status:
            stmt = stmt.where(RefundRequest.status == status)
        rows = (await self._session.execute(stmt)).all()
        return tuple(self._refund_from(row[0], row[1]) for row in rows)

    async def review_refund(
        self,
        *,
        shop_id: UUID,
        refund_id: UUID,
        reviewer_id: UUID,
        approve: bool,
        review_note: str | None,
    ) -> RefundRow:
        """Approve or reject one ``requested`` refund (support permission required)."""
        stmt = (
            sa.select(RefundRequest)
            .where(RefundRequest.shop_id == shop_id, RefundRequest.id == refund_id)
            .with_for_update()
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise ToolError(ErrorCode.VALIDATION_ERROR, "未找到该退款申请。")
        if RefundStatus(str(row.status)) is not RefundStatus.REQUESTED:
            raise ToolError(ErrorCode.INVALID_STATE, "该退款申请已处理，不能重复审核。")
        if not approve and not (review_note or "").strip():
            raise ToolError(ErrorCode.VALIDATION_ERROR, "拒绝退款时必须填写说明。")
        row.status = RefundStatus.APPROVED if approve else RefundStatus.REJECTED
        row.review_note = review_note or None
        row.reviewed_by = reviewer_id
        row.reviewed_at = datetime.now(UTC)
        await self._session.commit()
        return await self._refund_row(refund_id)

    # -- internals ---------------------------------------------------------
    async def _row(self, order: Order) -> OrderRow:
        items = await self._items(shop_id=order.shop_id, order_id=order.id)
        return OrderRow(
            id=order.id,
            order_no=order.order_no,
            status=str(order.status),
            total_cents=int(order.total_cents),
            currency=order.currency,
            placed_at=order.placed_at,
            paid_at=order.paid_at,
            delivered_at=order.delivered_at,
            cancelled_at=order.cancelled_at,
            updated_at=order.updated_at,
            is_synthetic=order.is_synthetic,
            lines=tuple(
                OrderLineRow(
                    id=item.id,
                    variant_id=item.variant_id,
                    sku=item.sku_snapshot,
                    title=item.title_snapshot,
                    quantity=item.quantity,
                    unit_price_cents=int(item.unit_price_cents),
                    line_total_cents=int(item.line_total_cents),
                    status=str(item.status),
                    is_returnable=item.is_returnable_snapshot,
                )
                for item in items
            ),
        )

    async def _items(self, *, shop_id: UUID, order_id: UUID) -> list[OrderItem]:
        stmt = (
            sa.select(OrderItem)
            .where(OrderItem.shop_id == shop_id, OrderItem.order_id == order_id)
            .order_by(OrderItem.created_at, OrderItem.id)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def _locked_order(self, *, shop_id: UUID, user_id: UUID, order_id: UUID) -> Order:
        stmt = (
            sa.select(Order)
            .where(Order.shop_id == shop_id, Order.user_id == user_id, Order.id == order_id)
            .with_for_update()
        )
        order = (await self._session.execute(stmt)).scalar_one_or_none()
        if order is None:
            raise _ORDER_NOT_FOUND
        return order

    async def _available_qty(self, *, shop_id: UUID, variant_id: UUID) -> int:
        stmt = sa.select(sa.func.coalesce(sa.func.sum(Inventory.available_qty), 0)).where(
            Inventory.shop_id == shop_id, Inventory.variant_id == variant_id
        )
        return int((await self._session.execute(stmt)).scalar() or 0)

    async def _take_stock(
        self, *, shop_id: UUID, variant_id: UUID, quantity: int, title: str
    ) -> None:
        stmt = (
            sa.select(Inventory)
            .where(Inventory.shop_id == shop_id, Inventory.variant_id == variant_id)
            .order_by(Inventory.available_qty.desc())
            .with_for_update()
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        total = sum(int(row.available_qty) for row in rows)
        if total < quantity:
            raise ToolError(
                ErrorCode.OUT_OF_STOCK,
                f"「{title}」库存不足，当前仅剩 {total} 件。",
            )
        remaining = quantity
        for row in rows:
            if remaining <= 0:
                break
            take = min(int(row.available_qty), remaining)
            row.available_qty = int(row.available_qty) - take
            remaining -= take

    async def _restore_stock(self, *, shop_id: UUID, variant_id: UUID, quantity: int) -> None:
        stmt = (
            sa.select(Inventory)
            .where(Inventory.shop_id == shop_id, Inventory.variant_id == variant_id)
            .order_by(Inventory.available_qty.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            row.available_qty = int(row.available_qty) + quantity

    async def _next_number(self, prefix: str, model: Any, column: Any) -> str:
        """Allocate a human-readable sequential number inside one transaction."""
        await self._session.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"{prefix}:number"}
        )
        latest = (await self._session.execute(sa.select(sa.func.max(column)))).scalar()
        seq = 1
        if isinstance(latest, str) and "-" in latest:
            tail = latest.rsplit("-", 1)[-1]
            if tail.isdigit():
                seq = int(tail) + 1
        return f"{prefix}-{seq:05d}"

    async def _refund_row(self, refund_id: UUID) -> RefundRow:
        stmt = (
            sa.select(RefundRequest, Order.order_no)
            .join(
                Order,
                sa.and_(Order.id == RefundRequest.order_id, Order.shop_id == RefundRequest.shop_id),
            )
            .where(RefundRequest.id == refund_id)
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:  # pragma: no cover - just written in this transaction
            raise ToolError(ErrorCode.VALIDATION_ERROR, "未找到该退款申请。")
        return self._refund_from(row[0], row[1])

    @staticmethod
    def _refund_from(row: RefundRequest, order_no: str) -> RefundRow:
        return RefundRow(
            id=row.id,
            refund_no=row.refund_no,
            order_id=row.order_id,
            order_no=order_no,
            order_item_id=row.order_item_id,
            scope=row.scope,
            status=str(row.status),
            reason_code=str(row.reason_code),
            amount_cents=int(row.amount_cents),
            note=row.note,
            review_note=row.review_note,
            created_at=row.created_at,
            updated_at=row.updated_at,
            reviewed_at=row.reviewed_at,
        )


__all__ = [
    "CartLine",
    "CheckoutRepository",
    "OrderLineRow",
    "OrderRow",
    "RefundRow",
]
