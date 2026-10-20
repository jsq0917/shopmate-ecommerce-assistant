"""Return eligibility and application endpoints (docs/06-api.md section 10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
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
    CreateReturnData,
    CreateReturnRequest,
    ReturnEligibilityData,
    ReturnEligibilityRequest,
)
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.domain.idempotency import OPERATION_CREATE_RETURN
from shopmate_ecommerce_assistant.tools.context import ConfirmationGrant
from shopmate_ecommerce_assistant.tools.dispatcher import ToolDispatcher
from shopmate_ecommerce_assistant.tools.order_schemas import (
    CheckReturnEligibilityInput,
    CreateReturnRequestInput,
)
from shopmate_ecommerce_assistant.tools.schemas import ToolFailure

router = APIRouter(prefix="/api/v1/returns", tags=["returns"])


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


@router.post("/eligibility", response_model=Envelope[ReturnEligibilityData])
async def check_eligibility(
    body: ReturnEligibilityRequest,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Envelope[ReturnEligibilityData]:
    request_id, trace_id = get_request_ids(request)
    dispatcher = ToolDispatcher(session=session, settings=settings)
    tctx = build_tool_context(context, request_id=request_id, trace_id=trace_id)
    result = await dispatcher.invoke(
        "check_return_eligibility",
        CheckReturnEligibilityInput(
            order_id=body.order_id, order_item_id=body.order_item_id, reason_code=body.reason_code
        ),
        context=tctx,
    )
    if isinstance(result, ToolFailure):
        _raise_failure(result)

    data = result.data or {}
    return Envelope(
        data=ReturnEligibilityData(
            decision=data.get("decision"),
            decision_code=data.get("decision_code"),
            error_code=data.get("error_code"),
            eligible=bool(data.get("eligible")),
            needs_clarification=bool(data.get("needs_clarification")),
            needs_manual_review=bool(data.get("needs_manual_review")),
            can_create_return_request=bool(data.get("can_create_return_request")),
            handoff_required=bool(data.get("handoff_required")),
            matched_rule_codes=list(data.get("matched_rule_codes") or []),
            deadline_at=data.get("deadline_at"),
            required_materials=list(data.get("required_materials") or []),
            next_action=data.get("next_action"),
            eligibility_token=data.get("eligibility_token"),
            eligibility_expires_at=data.get("eligibility_expires_at"),
            rule_version=data.get("rule_version"),
            evaluated_at=data.get("evaluated_at"),
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post("", response_model=Envelope[CreateReturnData], status_code=status.HTTP_201_CREATED)
async def create_return(
    body: CreateReturnRequest,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Envelope[CreateReturnData]:
    if not idempotency_key:
        raise ToolError(ErrorCode.VALIDATION_ERROR, "缺少 Idempotency-Key 请求头。")

    request_id, trace_id = get_request_ids(request)
    dispatcher = ToolDispatcher(session=session, settings=settings)
    confirmation = ConfirmationGrant(
        operation=OPERATION_CREATE_RETURN,
        order_id=body.order_id,
        order_item_id=body.order_item_id,
        reason_code=body.reason_code.value,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.eligibility_token_ttl_seconds),
    )
    tctx = build_tool_context(
        context,
        request_id=request_id,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
        route_confidence=1.0,
        confirmation=confirmation,
    )
    result = await dispatcher.invoke(
        "create_return_request",
        CreateReturnRequestInput(
            order_id=body.order_id,
            order_item_id=body.order_item_id,
            reason_code=body.reason_code,
            eligibility_token=body.eligibility_token,
        ),
        context=tctx,
    )
    if isinstance(result, ToolFailure):
        _raise_failure(result)

    data = result.data or {}
    return Envelope(
        data=CreateReturnData(
            return_request_id=data.get("return_request_id"),
            status="submitted",
            submitted_at=data.get("submitted_at"),
            review_required=bool(data.get("review_required")),
            required_materials=list(data.get("required_materials") or []),
            next_action=data.get("next_action"),
            refund_status="not_created",
            notice=data.get("notice"),
            idempotent_replay=bool(result.idempotent_replay),
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


__all__ = ["router"]
