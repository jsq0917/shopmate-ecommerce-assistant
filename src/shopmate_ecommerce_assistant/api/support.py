"""Support workbench endpoints (docs/06-api.md section 12).

Access model (contract §12, enforced here **and** in the repository):

* tickets need ``support:ticket:read`` / ``support:ticket:write``;
* a transcript needs ``support:conversation:read`` **and** an authorising ticket in the
  caller's shop — there is no "list every consumer conversation" endpoint, and ``admin``
  does not carry the support permissions by default;
* quality labels need ``support:quality_label:write`` plus message ownership.

Every write records an ``audit_events`` row through the existing audit repository.
Responses never include full PII, the system prompt, keys or internal stacks: owner and
assignee are masked, and message content goes through :func:`mask_pii`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.api.deps import (
    get_request_ids,
    get_session,
    require_permission,
)
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import (
    QualityLabelData,
    QualityLabelRequest,
    RefundItem,
    RefundListData,
    RefundReviewRequest,
    SupportConversationData,
    SupportConversationMessageItem,
    SupportHandoffSummary,
    SupportReplyData,
    SupportReplyRequest,
    SupportTicketDetail,
    SupportTicketItem,
    SupportTicketListData,
    SupportTicketPatchData,
    SupportTicketPatchRequest,
    SupportToolCallItem,
)
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.models import Conversation
from shopmate_ecommerce_assistant.db.repositories.audit import AuditRepository
from shopmate_ecommerce_assistant.db.repositories.checkout import CheckoutRepository, RefundRow
from shopmate_ecommerce_assistant.db.repositories.conversations import MessageRepository
from shopmate_ecommerce_assistant.db.repositories.support import (
    InvalidTicketTransition,
    SupportRepository,
    SupportTicketRow,
    UnknownAssignee,
)
from shopmate_ecommerce_assistant.domain.audit.models import AuditEventRecord

router = APIRouter(prefix="/api/v1/support", tags=["support"])

TicketReader = Annotated[AccessContext, Depends(require_permission("support:ticket:read"))]
TicketWriter = Annotated[AccessContext, Depends(require_permission("support:ticket:write"))]
ConversationReader = Annotated[
    AccessContext, Depends(require_permission("support:conversation:read"))
]
LabelWriter = Annotated[
    AccessContext, Depends(require_permission("support:quality_label:write"))
]

_TICKET_NOT_FOUND = "未找到可由当前账号访问的人工工单。"


def _item(row: SupportTicketRow) -> SupportTicketItem:
    return SupportTicketItem(
        ticket_id=row.ticket_id,
        status=row.status,
        risk_level=row.risk_level,
        primary_reason_code=row.primary_reason_code,
        reason_codes=list(row.reason_codes),
        priority=row.priority,
        queue=row.queue,
        conversation_id=row.conversation_id,
        user_reference_masked=row.user_reference_masked,
        assigned_to_masked=row.assigned_to_masked,
        created_at=row.created_at,
        waiting_seconds=row.waiting_seconds,
    )


async def _audit(
    session: AsyncSession,
    *,
    context: AccessContext,
    action: str,
    resource_type: str,
    resource_id: UUID,
    request_id: UUID,
    trace_id: UUID,
    metadata: dict[str, object],
) -> None:
    await AuditRepository(session).record_event(
        AuditEventRecord(
            id=uuid4(),
            shop_id=context.shop_id,
            actor_user_id=context.user_id,
            actor_role=context.role.value,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id,
            trace_id=trace_id,
            outcome="succeeded",
            metadata=metadata,
        )
    )


@router.get("/tickets", response_model=Envelope[SupportTicketListData])
async def list_tickets(
    request: Request,
    context: TicketReader,
    session: Annotated[AsyncSession, Depends(get_session)],
    ticket_status: Annotated[str | None, Query(alias="status")] = None,
    risk_level: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Envelope[SupportTicketListData]:
    """Return the risk/age ordered ticket queue for the caller's shop."""
    repo = SupportRepository(session)
    rows = await repo.list_tickets(
        shop_id=context.shop_id,
        status=ticket_status,
        risk_level=risk_level,
        limit=limit,
        offset=offset,
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=SupportTicketListData(
            items=[_item(row) for row in rows],
            next_offset=offset + limit if len(rows) == limit else None,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.get("/tickets/{ticket_id}", response_model=Envelope[SupportTicketDetail])
async def get_ticket(
    ticket_id: UUID,
    request: Request,
    context: TicketReader,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[SupportTicketDetail]:
    repo = SupportRepository(session)
    row = await repo.get_ticket(shop_id=context.shop_id, ticket_id=ticket_id)
    if row is None:
        raise ToolError(ErrorCode.CONVERSATION_NOT_FOUND, _TICKET_NOT_FOUND)
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=SupportTicketDetail(
            ticket_id=row.ticket_id,
            status=row.status,
            risk_level=row.risk_level,
            primary_reason_code=row.primary_reason_code,
            reason_codes=list(row.reason_codes),
            priority=row.priority,
            queue=row.queue,
            conversation_id=row.conversation_id,
            user_reference_masked=row.user_reference_masked,
            assigned_to_masked=row.assigned_to_masked,
            created_at=row.created_at,
            updated_at=row.updated_at,
            waiting_seconds=row.waiting_seconds,
            summary_redacted=row.summary_redacted,
            expected_response=row.expected_response,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.patch("/tickets/{ticket_id}", response_model=Envelope[SupportTicketPatchData])
async def patch_ticket(
    ticket_id: UUID,
    body: SupportTicketPatchRequest,
    request: Request,
    context: TicketWriter,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[SupportTicketPatchData]:
    """Apply one legal transition (``assign``/``resolve``/``close``)."""
    repo = SupportRepository(session)
    existing = await repo.get_ticket(shop_id=context.shop_id, ticket_id=ticket_id)
    if existing is None:
        raise ToolError(ErrorCode.CONVERSATION_NOT_FOUND, _TICKET_NOT_FOUND)
    try:
        row = await repo.transition(
            shop_id=context.shop_id,
            ticket_id=ticket_id,
            actor_user_id=context.user_id,
            action=body.action,
            assignee_user_id=body.assignee_user_id,
            resolution_summary=body.resolution_summary,
            close_reason=body.close_reason,
        )
    except InvalidTicketTransition as exc:
        raise ToolError(
            ErrorCode.INVALID_STATE,
            f"工单当前状态为 {existing.status}，不能执行该操作。",
        ) from exc
    except UnknownAssignee as exc:
        raise ToolError(
            ErrorCode.FORBIDDEN, "指定客服不在当前店铺或没有客服权限。"
        ) from exc

    request_id, trace_id = get_request_ids(request)
    await _audit(
        session,
        context=context,
        action=f"support.ticket.{body.action}",
        resource_type="handoff_ticket",
        resource_id=ticket_id,
        request_id=request_id,
        trace_id=trace_id,
        metadata={
            "from_status": existing.status,
            "to_status": row.status,
            "has_resolution_summary": body.resolution_summary is not None,
            "has_close_reason": body.close_reason is not None,
        },
    )
    return Envelope(
        data=SupportTicketPatchData(
            ticket_id=row.ticket_id,
            status=row.status,
            assigned_to_masked=row.assigned_to_masked,
            updated_at=row.updated_at,
            request_id=request_id,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.get("/conversations/{conversation_id}", response_model=Envelope[SupportConversationData])
async def get_conversation(
    conversation_id: UUID,
    request: Request,
    context: ConversationReader,
    session: Annotated[AsyncSession, Depends(get_session)],
    message_limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> Envelope[SupportConversationData]:
    """Return the transcript that an authorised ticket provides a business reason for."""
    repo = SupportRepository(session)
    ticket = await repo.get_ticket_for_conversation(
        shop_id=context.shop_id, conversation_id=conversation_id
    )
    if ticket is None:
        raise ToolError(
            ErrorCode.CONVERSATION_NOT_FOUND, "未找到与该会话关联且可访问的人工工单。"
        )
    row = await repo.get_conversation(
        shop_id=context.shop_id,
        conversation_id=conversation_id,
        ticket=ticket,
        message_limit=message_limit,
    )
    if row is None:
        raise ToolError(ErrorCode.CONVERSATION_NOT_FOUND, "未找到该会话。")
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=SupportConversationData(
            conversation_id=row.conversation_id,
            title=row.title,
            owner_reference_masked=row.owner_reference_masked,
            target_user_id=row.target_user_id,
            ticket_id=row.ticket_id,
            messages=[
                SupportConversationMessageItem(
                    message_id=message.message_id,
                    role=message.role,
                    content=message.content,
                    is_complete=message.is_complete,
                    citations=message.citations,
                    risk=message.risk,
                    created_at=message.created_at,
                )
                for message in row.messages
            ],
            tool_calls=[
                SupportToolCallItem(
                    tool_call_id=call.tool_call_id,
                    tool_name=call.tool_name,
                    status=call.status,
                    latency_ms=call.latency_ms,
                    result_summary=call.result_summary,
                )
                for call in row.tool_calls
            ],
            handoff=SupportHandoffSummary(
                ticket_id=row.ticket_id,
                status=row.ticket_status,
                primary_reason_code=row.ticket_primary_reason_code,
            ),
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post(
    "/messages/{message_id}/quality-labels",
    response_model=Envelope[QualityLabelData],
)
async def label_message(
    message_id: UUID,
    body: QualityLabelRequest,
    request: Request,
    context: LabelWriter,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[QualityLabelData]:
    """Record ``correct/incorrect/needs_knowledge`` for one authorised assistant answer."""
    repo = SupportRepository(session)
    message = await repo.get_authorised_assistant_message(
        shop_id=context.shop_id, message_id=message_id
    )
    if message is None:
        raise ToolError(
            ErrorCode.CONVERSATION_NOT_FOUND,
            "未找到可由当前账号标记的助手消息。",
        )
    ticket = await repo.get_ticket_for_conversation(
        shop_id=context.shop_id, conversation_id=message.conversation_id
    )
    assert ticket is not None  # guaranteed by get_authorised_assistant_message
    row = await repo.upsert_quality_label(
        shop_id=context.shop_id,
        ticket_id=ticket.id,
        conversation_id=message.conversation_id,
        message_id=message.id,
        label=body.label,
        reason_summary=body.reason_summary,
        labeled_by=context.user_id,
    )
    request_id, trace_id = get_request_ids(request)
    await _audit(
        session,
        context=context,
        action="support.quality_label.write",
        resource_type="message",
        resource_id=message.id,
        request_id=request_id,
        trace_id=trace_id,
        metadata={"label": row.label, "has_reason": body.reason_summary is not None},
    )
    return Envelope(
        data=QualityLabelData(message_id=row.message_id, label=row.label),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post(
    "/tickets/{ticket_id}/reply",
    response_model=Envelope[SupportReplyData],
    status_code=status.HTTP_201_CREATED,
)
async def reply_to_ticket(
    ticket_id: UUID,
    body: SupportReplyRequest,
    request: Request,
    context: TicketWriter,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[SupportReplyData]:
    """Append one human-agent reply to the ticket's conversation.

    The reply is stored as an ``assistant`` message with ``route='support_agent'`` so the
    shopper sees it in the same thread, and it is labelled in ``risk_jsonb`` so the UI can
    render it as "人工客服" rather than as an AI answer. The conversation owner is looked up
    from the conversation row (never from the body) and the message keeps the owner's
    ``user_id`` so the shopper's transcript query still finds it.
    """
    repo = SupportRepository(session)
    ticket = await repo.get_ticket(shop_id=context.shop_id, ticket_id=ticket_id)
    if ticket is None:
        raise ToolError(ErrorCode.CONVERSATION_NOT_FOUND, _TICKET_NOT_FOUND)
    owner_id = (
        await session.execute(
            sa.select(Conversation.user_id).where(
                Conversation.shop_id == context.shop_id,
                Conversation.id == ticket.conversation_id,
            )
        )
    ).scalar_one_or_none()
    if owner_id is None:
        raise ToolError(ErrorCode.CONVERSATION_NOT_FOUND, "未找到该工单对应的会话。")

    agent_label = context.user_id.hex[:6]
    message = await MessageRepository(session).insert_assistant_message(
        shop_id=context.shop_id,
        conversation_id=ticket.conversation_id,
        user_id=owner_id,
        content=body.content.strip(),
        route="support_agent",
        finish_reason="human_reply",
        citations={},
        risk={
            "author": "support_agent",
            "agent_reference_masked": f"客服{agent_label}",
            "risk_level": "low",
            "ticket_id": str(ticket_id),
        },
        is_complete=True,
    )
    await session.execute(
        sa.update(Conversation)
        .where(Conversation.shop_id == context.shop_id, Conversation.id == ticket.conversation_id)
        .values(updated_at=sa.func.now())
    )
    await session.commit()

    request_id, trace_id = get_request_ids(request)
    await _audit(
        session,
        context=context,
        action="support.ticket.reply",
        resource_type="handoff_ticket",
        resource_id=ticket_id,
        request_id=request_id,
        trace_id=trace_id,
        metadata={"message_id": str(message.id), "length": len(message.content)},
    )
    return Envelope(
        data=SupportReplyData(
            message_id=message.id,
            conversation_id=ticket.conversation_id,
            created_at=message.created_at,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.get("/refunds", response_model=Envelope[RefundListData])
async def list_refunds(
    request: Request,
    context: TicketReader,
    session: Annotated[AsyncSession, Depends(get_session)],
    refund_status: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Envelope[RefundListData]:
    """Return refund applications waiting for a human decision (shop-wide)."""
    repo = CheckoutRepository(session)
    rows = await repo.list_shop_refunds(
        shop_id=context.shop_id, status=refund_status, limit=limit
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=RefundListData(items=[_refund_item(row) for row in rows]),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post("/refunds/{refund_id}/review", response_model=Envelope[RefundItem])
async def review_refund(
    refund_id: UUID,
    body: RefundReviewRequest,
    request: Request,
    context: TicketWriter,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[RefundItem]:
    """Approve or reject one refund application. Money never moves (simulated)."""
    repo = CheckoutRepository(session)
    row = await repo.review_refund(
        shop_id=context.shop_id,
        refund_id=refund_id,
        reviewer_id=context.user_id,
        approve=body.approve,
        review_note=body.review_note,
    )
    request_id, trace_id = get_request_ids(request)
    await _audit(
        session,
        context=context,
        action="support.refund.approve" if body.approve else "support.refund.reject",
        resource_type="refund_request",
        resource_id=refund_id,
        request_id=request_id,
        trace_id=trace_id,
        metadata={"status": row.status, "amount_cents": row.amount_cents},
    )
    return Envelope(data=_refund_item(row), request_id=request_id, trace_id=trace_id)


def _refund_item(row: RefundRow) -> RefundItem:
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


__all__ = ["router"]