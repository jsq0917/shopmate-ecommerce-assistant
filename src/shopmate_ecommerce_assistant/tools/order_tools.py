"""Read-only order and shipment tools.

Both tools re-check ownership in the repository query (``shop_id`` + ``user_id``), not in
the route or the prompt. A missing order and someone else's order produce the *same*
``ORDER_NOT_FOUND`` envelope with no order fields, so the caller cannot probe existence.

The timeline only contains timestamps the OMS actually stores (placed, delivered,
cancelled). Intermediate statuses are not invented: ``status`` plus ``status_updated_at``
already say where the order is now.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.domain.orders.models import OrderSnapshot, ShipmentSnapshot
from shopmate_ecommerce_assistant.domain.orders.ports import OrderReader
from shopmate_ecommerce_assistant.tools.context import ToolContext
from shopmate_ecommerce_assistant.tools.order_schemas import (
    GetOrderStatusInput,
    GetShipmentData,
    GetShipmentInput,
    OrderStatusData,
    OrderStatusEvent,
    ShipmentEventItem,
)
from shopmate_ecommerce_assistant.tools.runtime import ToolOutcome, ToolRuntime
from shopmate_ecommerce_assistant.tools.schemas import ToolSuccess
from shopmate_ecommerce_assistant.tools.validation import validate_input

ORDER_NOT_FOUND_MESSAGE = "未找到可由当前账号访问的订单。请核对订单号，或转人工协助。"
SHIPMENT_NOT_FOUND_MESSAGE = (
    "该订单暂无可查看的物流记录，当前无法确认配送进度。可稍后重试或转人工协助。"
)


class OrderTools:
    """``get_order_status`` and ``get_shipment``, sharing one shop-scoped reader."""

    def __init__(self, reader: OrderReader, *, runtime: ToolRuntime | None = None) -> None:
        self._reader = reader
        self._runtime = runtime or ToolRuntime()

    async def get_order_status(self, payload: object, *, context: ToolContext):
        """Return the current status, amount summary and known timestamps of one order."""
        return await self._runtime.execute(
            "get_order_status",
            context=context,
            payload=payload,
            handler=self._get_order_status,
        )

    async def _get_order_status(self, payload: object, context: ToolContext) -> ToolOutcome:
        params = validate_input(GetOrderStatusInput, payload)
        context.ensure_order_read()

        order = await self._reader.get_order(
            shop_id=context.shop_id,
            user_id=context.subject_user_id,
            order_id=params.order_id,
            order_no=params.order_no,
        )
        if order is None:
            raise ToolError(ErrorCode.ORDER_NOT_FOUND, ORDER_NOT_FOUND_MESSAGE)

        data = OrderStatusData(
            order_id=order.id,
            order_no=order.order_no,
            status=order.status.value,
            total_cents=order.total_cents,
            currency=order.currency,
            is_synthetic=order.is_synthetic,
            placed_at=order.placed_at,
            status_updated_at=order.updated_at,
            timeline=_timeline(order),
        )
        return ToolOutcome(
            ToolSuccess(
                tool_call_id=uuid4(),
                data=data.model_dump(mode="json"),
                as_of=order.updated_at,
                trace_id=context.trace_id,
            )
        )

    async def get_shipment(self, payload: object, *, context: ToolContext):
        """Return the carrier, masked tracking number and node timeline of one order."""
        return await self._runtime.execute(
            "get_shipment",
            context=context,
            payload=payload,
            handler=self._get_shipment,
        )

    async def _get_shipment(self, payload: object, context: ToolContext) -> ToolOutcome:
        params = validate_input(GetShipmentInput, payload)
        context.ensure_order_read()

        # Ownership first: the shipment query itself is keyed by order_id only, so it must
        # never run before the order has been proven to belong to this subject.
        order = await self._reader.get_order(
            shop_id=context.shop_id,
            user_id=context.subject_user_id,
            order_id=params.order_id,
        )
        if order is None:
            raise ToolError(ErrorCode.ORDER_NOT_FOUND, ORDER_NOT_FOUND_MESSAGE)

        shipment = await self._reader.get_shipment(shop_id=context.shop_id, order_id=order.id)
        if shipment is None:
            raise ToolError(ErrorCode.SHIPMENT_NOT_FOUND, SHIPMENT_NOT_FOUND_MESSAGE)

        data = _shipment_data(shipment)
        return ToolOutcome(
            ToolSuccess(
                tool_call_id=uuid4(),
                data=data.model_dump(mode="json"),
                as_of=shipment.updated_at,
                trace_id=context.trace_id,
            )
        )


def _timeline(order: OrderSnapshot) -> list[OrderStatusEvent]:
    """Return only the timestamps the order row really holds, de-duplicated by status."""
    stamps: dict[str, datetime] = {"created": order.placed_at}
    if order.delivered_at is not None:
        stamps["delivered"] = order.delivered_at
    if order.cancelled_at is not None:
        stamps["cancelled"] = order.cancelled_at
    return [
        OrderStatusEvent(status=status, occurred_at=occurred_at)
        for status, occurred_at in sorted(stamps.items(), key=lambda item: item[1])
    ]


def _shipment_data(shipment: ShipmentSnapshot) -> GetShipmentData:
    return GetShipmentData(
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
    )


__all__ = ["ORDER_NOT_FOUND_MESSAGE", "SHIPMENT_NOT_FOUND_MESSAGE", "OrderTools"]
