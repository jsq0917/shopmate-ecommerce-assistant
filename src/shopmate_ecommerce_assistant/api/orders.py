"""Order and shipment endpoints (docs/06-api.md section 9)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.api.deps import get_access_context, get_request_ids, get_session
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import (
    OrderDetailData,
    OrderItemSummary,
    OrderListData,
    OrderListItem,
    ShipmentData,
    ShipmentEventItem,
)
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.models.enums import OrderStatus
from shopmate_ecommerce_assistant.db.repositories.orders import OrderRepository

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

_ORDER_NOT_FOUND = ToolError(ErrorCode.ORDER_NOT_FOUND, "未找到可由当前账号访问的订单。")
_SHIPMENT_NOT_FOUND = ToolError(ErrorCode.SHIPMENT_NOT_FOUND, "该订单暂无可查看的物流记录。")


@router.get("", response_model=Envelope[OrderListData])
async def list_orders(
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Envelope[OrderListData]:
    repo = OrderRepository(session)
    order_status = None
    if status is not None:
        try:
            order_status = OrderStatus(status)
        except ValueError:
            raise ToolError(ErrorCode.VALIDATION_ERROR, "订单状态参数不合法。") from None

    orders = await repo.list_orders(
        shop_id=context.shop_id,
        user_id=context.user_id,
        status=order_status,
        limit=limit,
        offset=offset,
    )
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
                )
                for o in orders
            ],
            next_offset=offset + len(orders) if len(orders) == limit else None,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.get("/{order_id}", response_model=Envelope[OrderDetailData])
async def get_order(
    order_id: UUID,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[OrderDetailData]:
    repo = OrderRepository(session)
    order = await repo.get_order(
        shop_id=context.shop_id, user_id=context.user_id, order_id=order_id
    )
    if order is None:
        raise _ORDER_NOT_FOUND
    items = await repo.list_order_items(shop_id=context.shop_id, order_id=order.id)
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=OrderDetailData(
            id=order.id,
            order_no=order.order_no,
            status=order.status.value,
            total_cents=order.total_cents,
            currency=order.currency,
            is_synthetic=order.is_synthetic,
            placed_at=order.placed_at,
            status_updated_at=order.updated_at,
            items=[
                OrderItemSummary(
                    id=item.id,
                    sku=item.sku,
                    title=item.title,
                    quantity=item.quantity,
                    unit_price_cents=item.unit_price_cents,
                    status=item.status.value,
                )
                for item in items
            ],
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


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
