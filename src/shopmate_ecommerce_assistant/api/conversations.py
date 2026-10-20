"""Conversation and message-history endpoints (docs/06-api.md section 6.1)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.api.deps import (
    get_access_context,
    get_request_ids,
    get_session,
)
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import (
    ConversationItem,
    ConversationListData,
    CreateConversationRequest,
    MessageItem,
    MessageListData,
    RenameConversationRequest,
)
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.repositories.conversations import (
    ConversationRepository,
    MessageRepository,
)

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])

_NOT_FOUND = ToolError(ErrorCode.CONVERSATION_NOT_FOUND, "未找到可由当前账号访问的会话。")


@router.get("", response_model=Envelope[ConversationListData])
async def list_conversations(
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> Envelope[ConversationListData]:
    repo = ConversationRepository(session)
    rows, next_cursor = await repo.list(
        shop_id=context.shop_id, user_id=context.user_id, limit=limit, cursor=cursor
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=ConversationListData(
            items=[
                ConversationItem(
                    id=row.id,
                    title=row.title,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ],
            next_cursor=next_cursor,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post("", response_model=Envelope[ConversationItem], status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: CreateConversationRequest,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[ConversationItem]:
    repo = ConversationRepository(session)
    row = await repo.create(
        shop_id=context.shop_id,
        user_id=context.user_id,
        title=body.title or "新对话",
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=ConversationItem(
            id=row.id, title=row.title, created_at=row.created_at, updated_at=row.updated_at
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.patch("/{conversation_id}", response_model=Envelope[ConversationItem])
async def rename_conversation(
    conversation_id: UUID,
    body: RenameConversationRequest,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[ConversationItem]:
    repo = ConversationRepository(session)
    ok = await repo.rename(
        shop_id=context.shop_id,
        user_id=context.user_id,
        conversation_id=conversation_id,
        title=body.title,
    )
    if not ok:
        raise _NOT_FOUND
    row = await repo.get(
        shop_id=context.shop_id, user_id=context.user_id, conversation_id=conversation_id
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=ConversationItem(
            id=row.id, title=row.title, created_at=row.created_at, updated_at=row.updated_at
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    repo = ConversationRepository(session)
    ok = await repo.soft_delete(
        shop_id=context.shop_id, user_id=context.user_id, conversation_id=conversation_id
    )
    if not ok:
        raise _NOT_FOUND


@router.get("/{conversation_id}/messages", response_model=Envelope[MessageListData])
async def list_messages(
    conversation_id: UUID,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    before: Annotated[str | None, Query()] = None,
) -> Envelope[MessageListData]:
    conversations = ConversationRepository(session)
    row = await conversations.get(
        shop_id=context.shop_id, user_id=context.user_id, conversation_id=conversation_id
    )
    if row is None:
        raise _NOT_FOUND

    messages = MessageRepository(session)
    rows = await messages.list_history(
        shop_id=context.shop_id,
        conversation_id=conversation_id,
        user_id=context.user_id,
        limit=limit,
        before=before,
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=MessageListData(
            items=[
                MessageItem(
                    id=item.id,
                    role=item.role,
                    content=item.content,
                    route=item.route,
                    finish_reason=item.finish_reason,
                    citations=(
                        item.citations.get("items", []) if isinstance(item.citations, dict) else []
                    ),
                    risk=item.risk,
                    is_complete=item.is_complete,
                    created_at=item.created_at,
                    client_message_id=item.client_message_id,
                )
                for item in rows
            ],
            next_cursor=None,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


__all__ = ["router"]
