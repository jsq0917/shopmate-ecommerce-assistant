"""Knowledge-base picker endpoint for the chat page (docs/06-api.md §6.1, stage 18).

The course brief requires the chat page to let a user choose one or more knowledge bases.
:mod:`api.admin` already lists knowledge bases, but only for admins; a shopper needs the
same candidates without the admin fields. This router is the read-only, user-facing view:
the caller's shop and ``status=active`` only, no documents, no chunks, no write paths.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.api.deps import (
    get_access_context,
    get_request_ids,
    get_session,
)
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import (
    KnowledgeBaseOption,
    KnowledgeBaseOptionListData,
)
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.repositories.knowledge_scope import (
    KnowledgeScopeRepository,
)

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge"])


@router.get("", response_model=Envelope[KnowledgeBaseOptionListData])
async def list_selectable_knowledge_bases(
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[KnowledgeBaseOptionListData]:
    """List the knowledge bases the current user may select in a conversation.

    Visibility rule: same shop + ``status=active``. An empty list is legitimate (a shop
    without knowledge bases) and the chat page then sends no selection at all.
    """
    rows = await KnowledgeScopeRepository(session).list_active(shop_id=context.shop_id)
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=KnowledgeBaseOptionListData(
            items=[
                KnowledgeBaseOption(id=row.id, name=row.name, locale=row.locale, region=row.region)
                for row in rows
            ]
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


__all__ = ["router"]
