"""Order, shipment and self-service checkout endpoints.

Read paths keep using :class:`OrderRepository` (stage 9 semantics). The write paths added
in stage 17 (`POST /orders`, `/pay`, `/cancel`) go through :class:`CheckoutRepository`,
which owns the transactional stock rules. Every handler derives the subject from the
verified access token; nothing is read from the body.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.api.deps import (
    get_access_context,
    get_request_ids,
    get_session,
    rate_limit,
)
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import (
    CreateOrderRequest,
    OrderDetailData,
    OrderItemSummary,
    OrderListData,
    OrderListItem,
    ShipmentData,
    ShipmentEventItem,
)
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.models import OrderItem
from shopmate_ecommerce_assistant.db.models.enums import OrderStatus
from shopmate_ecommerce_assistant.db.repositories.checkout import (
    CartLine,
    CheckoutRepository,
    OrderRow,
)
from shopmate_ecommerce_assistant.db.repositories.orders import OrderRepository

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

_ORDER_NOT_FOUND = ToolError(ErrorCode.ORDER_NOT_FOUND, "未找到可由当前账号访问的订单。")
_SHIPMENT_NOT_FOUND = ToolError(ErrorCode.SHIPMENT_NOT_FOUND, "该订单暂无可查看的物流记录。")

#: A shopper may create at most 30 orders per minute; the write path touches stock.
_CHECKOUT_LIMIT = rate_limit(
    lambda request, context: f"checkout:{context.user_id if context else 'anon'}",
    limit=30,
    window=60,
)


def _detail(row: OrderRow) -> OrderDetailData:
    return OrderDetailData(
        id=row.id,
        order_no=row.order_no,
        status=row.status,
        total_cents=row.total_cents,
        currency=row.currency,
        is_synthetic=row.is_synthetic,
        placed_at=row.placed_at,
        paid_at=row.paid_at,
        status_updated_at=row.updated_at,
        items=[
            OrderItemSummary(
                id=line.id,
                sku=line.sku,
                title=line.title,
                quantity=line.quantity,
                unit_price_cents=line.unit_price_cents,
                status=line.status,
                is_returnable=line.is_returnable,
            )
            for line in row.lines
        ],
    )


@router.get("", response_model=Envelope[OrderListData])
async def list_orders(
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status_: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Envelope[OrderListData]:
    repo = OrderRepository(session)
    order_status = None
    if status_ is not None:
        try:
            order_status = OrderStatus(status_)
        except ValueError:
            raise ToolError(ErrorCode.VALIDATION_ERROR, "订单状态参数不合法。") from None

    orders = await repo.list_orders(
        shop_id=context.shop_id,
        user_id=context.user_id,
        status=order_status,
        limit=limit,
        offset=offset,
    )
    counts: dict[UUID, int] = {}
    first_titles: dict[UUID, str] = {}
    order_ids = [order.id for order in orders]
    if order_ids:
        count_rows = await session.execute(
            sa.select(OrderItem.order_id, sa.func.count())
            .where(OrderItem.shop_id == context.shop_id, OrderItem.order_id.in_(order_ids))
            .group_by(OrderItem.order_id)
        )
        counts = {row[0]: int(row[1]) for row in count_rows.all()}
        title_rows = await session.execute(
            sa.select(OrderItem.order_id, sa.func.min(OrderItem.title_snapshot))
            .where(OrderItem.shop_id == context.shop_id, OrderItem.order_id.in_(order_ids))
            .group_by(OrderItem.order_id)
        )
        first_titles = {row[0]: str(row[1]) for row in title_rows.all()}

    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=OrderListData(
            items=[
                OrderListItem(
                    id=o.id,
                    order_no=o.order_no,
                    status=o.status.value,
                    total_cents=o.total_cents,
                    currency=o.currency,
                    is_synthetic=o.is_synthetic,
                    placed_at=o.placed_at,
                    status_updated_at=o.updated_at,
                    item_count=counts.get(o.id, 0),
                    first_item_title=first_titles.get(o.id),
                )
                for o in orders
            ],
            next_offset=offset + len(orders) if len(orders) == limit else None,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post(
    "",
    response_model=Envelope[OrderDetailData],
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    body: CreateOrderRequest,
    request: Request,
    context: Annotated[AccessContext, Depends(_CHECKOUT_LIMIT)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[OrderDetailData]:
    """Place an order from selected SKUs. Stock is only reserved on payment."""
    repo = CheckoutRepository(session)
    row = await repo.create_order(
        shop_id=context.shop_id,
        user_id=context.user_id,
        lines=[CartLine(variant_id=item.variant_id, quantity=item.quantity) for item in body.items],
        shipping_address_masked=body.shipping_address_masked,
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(data=_detail(row), request_id=request_id, trace_id=trace_id)


@router.post("/{order_id}/pay", response_model=Envelope[OrderDetailData])
async def pay_order(
    order_id: UUID,
    request: Request,
    context: Annotated[AccessContext, Depends(_CHECKOUT_LIMIT)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[OrderDetailData]:
    """Simulated payment: moves ``created`` to ``paid`` and reserves stock."""
    repo = CheckoutRepository(session)
    row = await repo.pay_order(
        shop_id=context.shop_id, user_id=context.user_id, order_id=order_id
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(data=_detail(row), request_id=request_id, trace_id=trace_id)


@router.post("/{order_id}/cancel", response_model=Envelope[OrderDetailData])
async def cancel_order(
    order_id: UUID,
    request: Request,
    context: Annotated[AccessContext, Depends(_CHECKOUT_LIMIT)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[OrderDetailData]:
    """Cancel an unpaid/paid order; a paid one returns its reserved stock."""
    repo = CheckoutRepository(session)
    row = await repo.cancel_order(
        shop_id=context.shop_id, user_id=context.user_id, order_id=order_id
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(data=_detail(row), request_id=request_id, trace_id=trace_id)


@router.get("/{order_id}", response_model=Envelope[OrderDetailData])
async def get_order(
    order_id: UUID,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[OrderDetailData]:
    repo = CheckoutRepository(session)
    row = await repo.get_order(
        shop_id=context.shop_id, user_id=context.user_id, order_id=order_id
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(data=_detail(row), request_id=request_id, trace_id=trace_id)


@router.get("/{order_id}/shipment", response_model=Envelope[ShipmentData])
async def get_shipment(
    order_id: UUID,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[ShipmentData]:
    repo = OrderRepository(session)
    order = await repo.get_order(
        shop_id=context.shop_id, user_id=context.user_id, order_id=order_id
    )
    if order is None:
        raise _ORDER_NOT_FOUND
    shipment = await repo.get_shipment(shop_id=context.shop_id, order_id=order.id)
    if shipment is None:
        raise _SHIPMENT_NOT_FOUND
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=ShipmentData(
            order_id=shipment.order_id,
            shipment_id=shipment.id,
            carrier=shipment.carrier,
            tracking_no_masked=shipment.tracking_no_masked,
            status=shipment.status.value,
            is_synthetic=shipment.is_synthetic,
            shipped_at=shipment.shipped_at,
            estimated_delivery_at=shipment.estimated_delivery_at,
            delivered_at=shipment.delivered_at,
            status_updated_at=shipment.updated_at,
            events=[
                ShipmentEventItem(
                    status=event.status.value,
                    description=event.description,
                    occurred_at=event.occurred_at,
                )
                for event in shipment.events
            ],
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


__all__ = ["router"]
