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
    get_settings_dep,
)
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import (
    ConversationGenerationParams,
    ConversationItem,
    ConversationListData,
    CreateConversationRequest,
    MessageItem,
    MessageListData,
    RenameConversationRequest,
    UpdateGenerationParamsRequest,
    UpdateKnowledgeBasesRequest,
)
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.repositories.conversations import (
    ConversationRepository,
    MessageRepository,
)
from shopmate_ecommerce_assistant.db.repositories.knowledge_scope import (
    KnowledgeScopeRepository,
)

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])

_NOT_FOUND = ToolError(ErrorCode.CONVERSATION_NOT_FOUND, "未找到可由当前账号访问的会话。")


def _item(row) -> ConversationItem:
    return ConversationItem(
        id=row.id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
        knowledge_base_ids=list(row.knowledge_base_ids),
        generation_params=_generation_params(row),
    )


def _generation_params(row) -> ConversationGenerationParams:
    """Render the stored overrides, degrading to "nothing overridden" on a bad row.

    The write path validates every value, so a failure here means a row was edited behind
    the API's back; answering with the defaults is safer than failing the whole page.
    """
    try:
        return ConversationGenerationParams.model_validate(row.generation_params or {})
    except ValueError:  # pragma: no cover - defensive against hand-edited rows
        return ConversationGenerationParams()


async def _require_selectable(
    session: AsyncSession, context: AccessContext, ids: list[UUID]
) -> tuple[UUID, ...]:
    """Validate a knowledge-base selection; reject the whole request if any id is invalid.

    A knowledge base from another shop and a nonexistent one are indistinguishable on
    purpose (no existence leak), and a partial selection is never persisted.
    """
    selectable, rejected = await KnowledgeScopeRepository(session).selectable_ids(
        shop_id=context.shop_id, candidate_ids=ids
    )
    if rejected:
        raise ToolError(
            ErrorCode.KNOWLEDGE_BASE_NOT_SELECTABLE,
            "所选知识库不可用（不存在、不属于当前店铺或已停用），请刷新后重试。",
            retryable=False,
        )
    return selectable


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
            items=[_item(row) for row in rows],
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
    selection = await _require_selectable(session, context, body.knowledge_base_ids)
    repo = ConversationRepository(session)
    row = await repo.create(
        shop_id=context.shop_id,
        user_id=context.user_id,
        title=body.title or "新对话",
        knowledge_base_ids=selection,
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(data=_item(row), request_id=request_id, trace_id=trace_id)


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
    return Envelope(data=_item(row), request_id=request_id, trace_id=trace_id)


@router.patch("/{conversation_id}/knowledge-bases", response_model=Envelope[ConversationItem])
async def update_knowledge_bases(
    conversation_id: UUID,
    body: UpdateKnowledgeBasesRequest,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[ConversationItem]:
    """Replace the conversation's knowledge-base selection (stage 18).

    The selection is conversation-scoped: it affects subsequent turns only. Messages that
    were already answered keep the citations they were stored with, so switching the
    selection never rewrites history.
    """
    repo = ConversationRepository(session)
    existing = await repo.get(
        shop_id=context.shop_id, user_id=context.user_id, conversation_id=conversation_id
    )
    if existing is None:
        raise _NOT_FOUND
    selection = await _require_selectable(session, context, body.knowledge_base_ids)
    await repo.set_knowledge_base_ids(
        shop_id=context.shop_id,
        user_id=context.user_id,
        conversation_id=conversation_id,
        knowledge_base_ids=selection,
    )
    row = await repo.get(
        shop_id=context.shop_id, user_id=context.user_id, conversation_id=conversation_id
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(data=_item(row), request_id=request_id, trace_id=trace_id)


@router.patch("/{conversation_id}/generation-params", response_model=Envelope[ConversationItem])
async def update_generation_params(
    conversation_id: UUID,
    body: UpdateGenerationParamsRequest,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Envelope[ConversationItem]:
    """Merge generation-parameter overrides onto the conversation (stage 19).

    The overrides are conversation-scoped: they affect subsequent turns only, so an
    already-streamed answer keeps the parameters it was generated with. An omitted field
    keeps its stored value, an explicit ``null`` clears that override; the operator's
    ``llm_max_tokens_cap`` is the hard ceiling for ``max_tokens`` (rejected, not clamped,
    so the chat page can show why the value was refused).
    """
    repo = ConversationRepository(session)
    existing = await repo.get(
        shop_id=context.shop_id, user_id=context.user_id, conversation_id=conversation_id
    )
    if existing is None:
        raise _NOT_FOUND
    cap = settings.llm_max_tokens_cap
    if body.max_tokens is not None and body.max_tokens > cap:
        raise ToolError(
            ErrorCode.VALIDATION_ERROR,
            f"最长输出不能超过 {cap} tokens，请调小后重试。",
            retryable=False,
        )
    stored = dict(existing.generation_params)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            stored.pop(key, None)
        else:
            stored[key] = value
    await repo.set_generation_params(
        shop_id=context.shop_id,
        user_id=context.user_id,
        conversation_id=conversation_id,
        params=stored,
    )
    row = await repo.get(
        shop_id=context.shop_id, user_id=context.user_id, conversation_id=conversation_id
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(data=_item(row), request_id=request_id, trace_id=trace_id)


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
                    product_cards=item.cards,
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
