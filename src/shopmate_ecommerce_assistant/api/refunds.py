"""Refund applications (shopper side).

A refund is a *request*, never an automatic payout: the row is created ``requested`` and a
support agent decides. Duplicate open applications are rejected by the repository, which
makes retries idempotent without trusting a client key.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

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
    CreateRefundRequest,
    RefundItem,
    RefundListData,
)
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.repositories.checkout import CheckoutRepository, RefundRow

router = APIRouter(prefix="/api/v1/refunds", tags=["refunds"])

_REFUND_LIMIT = rate_limit(
    lambda request, context: f"refund:{context.user_id if context else 'anon'}",
    limit=20,
    window=60,
)


def _item(row: RefundRow) -> RefundItem:
    return RefundItem(
        id=row.id,
        refund_no=row.refund_no,
        order_id=row.order_id,
        order_no=row.order_no,
        order_item_id=row.order_item_id,
        scope=row.scope,
        status=row.status,
        reason_code=row.reason_code,
        amount_cents=row.amount_cents,
        note=row.note,
        review_note=row.review_note,
        created_at=row.created_at,
        updated_at=row.updated_at,
        reviewed_at=row.reviewed_at,
    )


@router.get("", response_model=Envelope[RefundListData])
async def list_refunds(
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    order_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Envelope[RefundListData]:
    repo = CheckoutRepository(session)
    rows = await repo.list_refunds(
        shop_id=context.shop_id, user_id=context.user_id, order_id=order_id, limit=limit
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=RefundListData(items=[_item(row) for row in rows]),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post(
    "",
    response_model=Envelope[RefundItem],
    status_code=status.HTTP_201_CREATED,
)
async def create_refund(
    body: CreateRefundRequest,
    request: Request,
    context: Annotated[AccessContext, Depends(_REFUND_LIMIT)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[RefundItem]:
    """Submit a refund application for review (no money moves here)."""
    repo = CheckoutRepository(session)
    row = await repo.create_refund(
        shop_id=context.shop_id,
        user_id=context.user_id,
        order_id=body.order_id,
        reason_code=body.reason_code,
        order_item_id=body.order_item_id,
        note=body.note,
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(data=_item(row), request_id=request_id, trace_id=trace_id)


__all__ = ["router"]
