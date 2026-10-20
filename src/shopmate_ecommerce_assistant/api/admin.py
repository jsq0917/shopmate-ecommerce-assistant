"""Admin knowledge management endpoints (docs/06-api.md section 13).

These are the stage-10 *skeletons*: they expose shop-scoped reads and metadata writes for
knowledge bases, documents, chunks and evaluation runs. The heavy upload/parse/index
pipeline remains the stage 5/7 ingestion path.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.api.deps import get_request_ids, get_session, require_role
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import (
    ChunkListData,
    ChunkListItem,
    CreateEvalRunData,
    CreateEvalRunRequest,
    CreateKnowledgeBaseRequest,
    DocumentListData,
    DocumentListItem,
    EvalRunItem,
    EvalRunListData,
    KnowledgeBaseItem,
    KnowledgeBaseListData,
    ModelProfileItem,
    ModelProfileListData,
)
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.models.enums import UserRole
from shopmate_ecommerce_assistant.db.repositories.knowledge_admin import KnowledgeAdminRepository

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

Admin = Annotated[AccessContext, Depends(require_role(UserRole.ADMIN))]


@router.get("/knowledge-bases", response_model=Envelope[KnowledgeBaseListData])
async def list_knowledge_bases(
    request: Request, context: Admin, session: Annotated[AsyncSession, Depends(get_session)]
) -> Envelope[KnowledgeBaseListData]:
    repo = KnowledgeAdminRepository(session)
    rows = await repo.list_knowledge_bases(shop_id=context.shop_id)
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=KnowledgeBaseListData(
            items=[
                KnowledgeBaseItem(
                    id=row.id,
                    name=row.name,
                    locale=row.locale,
                    region=row.region,
                    status=row.status,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post(
    "/knowledge-bases",
    response_model=Envelope[KnowledgeBaseItem],
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_base(
    body: CreateKnowledgeBaseRequest,
    request: Request,
    context: Admin,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[KnowledgeBaseItem]:
    repo = KnowledgeAdminRepository(session)
    row = await repo.create_knowledge_base(
        shop_id=context.shop_id, name=body.name, locale=body.locale, region=body.region
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=KnowledgeBaseItem(
            id=row.id,
            name=row.name,
            locale=row.locale,
            region=row.region,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.get("/documents", response_model=Envelope[DocumentListData])
async def list_documents(
    request: Request,
    context: Admin,
    session: Annotated[AsyncSession, Depends(get_session)],
    knowledge_base_id: Annotated[UUID | None, Query()] = None,
) -> Envelope[DocumentListData]:
    repo = KnowledgeAdminRepository(session)
    rows = await repo.list_documents(shop_id=context.shop_id, knowledge_base_id=knowledge_base_id)
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=DocumentListData(items=[_doc_item(row) for row in rows]),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.get("/documents/{document_id}", response_model=Envelope[DocumentListItem])
async def get_document(
    document_id: UUID,
    request: Request,
    context: Admin,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[DocumentListItem]:
    repo = KnowledgeAdminRepository(session)
    row = await repo.get_document(shop_id=context.shop_id, document_id=document_id)
    if row is None:
        from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError

        raise ToolError(ErrorCode.CONVERSATION_NOT_FOUND, "未找到该文档。")
    request_id, trace_id = get_request_ids(request)
    return Envelope(data=_doc_item(row), request_id=request_id, trace_id=trace_id)


@router.get("/chunks", response_model=Envelope[ChunkListData])
async def list_chunks(
    request: Request,
    context: Admin,
    session: Annotated[AsyncSession, Depends(get_session)],
    document_id: Annotated[UUID | None, Query()] = None,
    version_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Envelope[ChunkListData]:
    repo = KnowledgeAdminRepository(session)
    rows = await repo.list_chunks(
        shop_id=context.shop_id, document_id=document_id, version_id=version_id, limit=limit
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=ChunkListData(
            items=[
                ChunkListItem(
                    chunk_id=row.chunk_id,
                    document_id=row.document_id,
                    version_id=row.version_id,
                    chunk_index=row.chunk_index,
                    heading_path=list(row.heading_path),
                    page_no=row.page_no,
                    text=row.text,
                    token_count=row.token_count,
                    is_enabled=row.is_enabled,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.get("/eval/runs", response_model=Envelope[EvalRunListData])
async def list_eval_runs(
    request: Request, context: Admin, session: Annotated[AsyncSession, Depends(get_session)]
) -> Envelope[EvalRunListData]:
    repo = KnowledgeAdminRepository(session)
    rows = await repo.list_eval_runs(shop_id=context.shop_id)
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=EvalRunListData(
            items=[
                EvalRunItem(
                    eval_run_id=row.id,
                    dataset_name=row.dataset_name,
                    dataset_version=row.dataset_version,
                    status=row.status,
                    metrics=row.metrics,
                    created_by=row.created_by,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post(
    "/eval/run",
    response_model=Envelope[CreateEvalRunData],
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_eval_run(
    body: CreateEvalRunRequest,
    request: Request,
    context: Admin,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[CreateEvalRunData]:
    repo = KnowledgeAdminRepository(session)
    row = await repo.create_eval_run(
        shop_id=context.shop_id,
        dataset_name=body.dataset_name,
        dataset_version=body.dataset_version,
        config={
            "config_profile_id": (str(body.config_profile_id) if body.config_profile_id else None),
            "seed": body.seed,
        },
        created_by=context.user_id,
    )
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=CreateEvalRunData(eval_run_id=row.id, status="queued", created_at=row.created_at),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.get("/model-profiles", response_model=Envelope[ModelProfileListData])
async def model_profiles(
    request: Request, context: Admin, session: Annotated[AsyncSession, Depends(get_session)]
) -> Envelope[ModelProfileListData]:
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=ModelProfileListData(
            items=[
                ModelProfileItem(
                    profile_id="answer-model",
                    model_name="shopmate-answer",
                    provider="openai-compatible",
                    supports_structured_tools=True,
                    is_synthetic=True,
                )
            ]
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


def _doc_item(row) -> DocumentListItem:
    return DocumentListItem(
        document_id=row.document_id,
        title=row.title,
        doc_type=row.doc_type,
        knowledge_base_id=row.knowledge_base_id,
        status=row.status,
        locale=row.locale,
        region=row.region,
        current_version_id=row.current_version_id,
        current_version=row.current_version,
        parse_status=row.parse_status,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        updated_at=row.updated_at,
        is_synthetic=row.is_synthetic,
    )


__all__ = ["router"]
