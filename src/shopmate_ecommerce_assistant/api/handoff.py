"""Consumer human-handoff endpoints (docs/06-api.md section 11)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.api.deps import (
    build_tool_context,
    get_access_context,
    get_request_ids,
    get_session,
    get_settings_dep,
)
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import (
    CreateHandoffData,
    CreateHandoffRequest,
    HandoffListData,
    HandoffListItem,
)
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.repositories.handoff_read import HandoffReadRepository
from shopmate_ecommerce_assistant.tools.dispatcher import ToolDispatcher
from shopmate_ecommerce_assistant.tools.order_schemas import CreateHandoffTicketInput
from shopmate_ecommerce_assistant.tools.schemas import ToolFailure

router = APIRouter(prefix="/api/v1/handoff", tags=["handoff"])

_TICKET_NOT_FOUND = ToolError(
    ErrorCode.CONVERSATION_NOT_FOUND, "未找到可由当前账号访问的人工工单。"
)


def _raise_failure(result: ToolFailure) -> None:
    try:
        code = ErrorCode(result.error_code or ErrorCode.INTERNAL_ERROR.value)
    except ValueError:
        code = ErrorCode.INTERNAL_ERROR
    raise ToolError(
        code,
        result.user_message,
        retryable=result.retryable,
        retry_after_ms=result.retry_after_ms,
    )


def _to_item(row) -> HandoffListItem:
    return HandoffListItem(
        ticket_id=row.id,
        status=row.status,
        risk_level=row.risk_level,
        primary_reason_code=row.primary_reason_code,
        reason_codes=list(row.reason_codes),
        priority=row.priority,
        queue=row.queue,
        summary_redacted=row.summary_redacted,
        expected_response=row.expected_response,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=Envelope[HandoffListData])
async def list_handoff(
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Envelope[HandoffListData]:
    repo = HandoffReadRepository(session)
    rows = await repo.list_for_user(
        shop_id=context.shop_id, user_id=context.user_id, limit=limit, offset=offset
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=HandoffListData(
            items=[_to_item(row) for row in rows],
            next_offset=offset + len(rows) if len(rows) == limit else None,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.get("/{ticket_id}", response_model=Envelope[HandoffListItem])
async def get_handoff(
    ticket_id: UUID,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[HandoffListItem]:
    repo = HandoffReadRepository(session)
    row = await repo.get_for_user(
        shop_id=context.shop_id, user_id=context.user_id, ticket_id=ticket_id
    )
    if row is None:
        raise _TICKET_NOT_FOUND
    request_id, trace_id = get_request_ids(request)
    return Envelope(data=_to_item(row), request_id=request_id, trace_id=trace_id)


@router.post("", response_model=Envelope[CreateHandoffData], status_code=status.HTTP_201_CREATED)
async def create_handoff(
    body: CreateHandoffRequest,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Envelope[CreateHandoffData]:
    if not idempotency_key:
        raise ToolError(ErrorCode.VALIDATION_ERROR, "缺少 Idempotency-Key 请求头。")

    request_id, trace_id = get_request_ids(request)
    dispatcher = ToolDispatcher(session=session, settings=settings)
    tctx = build_tool_context(
        context,
        request_id=request_id,
        trace_id=trace_id,
        conversation_id=body.conversation_id,
        idempotency_key=idempotency_key,
    )
    result = await dispatcher.invoke(
        "create_handoff_ticket",
        CreateHandoffTicketInput(
            conversation_id=body.conversation_id,
            reason_code=body.reason_code,
            summary_redacted=body.summary_redacted,
        ),
        context=tctx,
    )
    if isinstance(result, ToolFailure):
        _raise_failure(result)

    data = result.data or {}
    return Envelope(
        data=CreateHandoffData(
            ticket_id=data.get("ticket_id"),
            status="open",
            risk_level=data.get("risk_level"),
            priority=data.get("priority"),
            queue=data.get("queue"),
            primary_reason_code=data.get("primary_reason_code"),
            reason_codes=list(data.get("reason_codes") or []),
            expected_response=data.get("expected_response"),
            created_at=data.get("created_at"),
            idempotent_replay=bool(result.idempotent_replay),
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


__all__ = ["router"]
