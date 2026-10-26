"""Admin knowledge management endpoints (docs/06-api.md section 13).

These are the stage-10 *skeletons*: they expose shop-scoped reads and metadata writes for
knowledge bases, documents, chunks and evaluation runs. The heavy upload/parse/index
pipeline remains the stage 5/7 ingestion path.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.api.deps import get_request_ids, get_session, require_role
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import (
    ChunkListData,
    ChunkListItem,
    ChunkPatchData,
    ChunkPatchRequest,
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
    ReindexData,
    UploadDocumentData,
)
from shopmate_ecommerce_assistant.core import paths
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.models.enums import KnowledgeDocType, UserRole
from shopmate_ecommerce_assistant.db.repositories.audit import AuditRepository
from shopmate_ecommerce_assistant.db.repositories.knowledge_admin import KnowledgeAdminRepository
from shopmate_ecommerce_assistant.domain.audit.models import AuditEventRecord
from shopmate_ecommerce_assistant.rag.ingest.loaders import IMAGE_MAX_BYTES, SUPPORTED_SUFFIXES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

Admin = Annotated[AccessContext, Depends(require_role(UserRole.ADMIN))]

_LOCALE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
_REGION = re.compile(r"^[A-Z]{2}$")
_UNSAFE_NAME = re.compile(r"[\\/]|\.\.")


def _read_upload_limit() -> int:
    from shopmate_ecommerce_assistant.core.config import get_settings

    return get_settings().knowledge_upload_max_bytes


#: Suffixes handled by the OCR loader (stage 20).
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})


def _upload_limit_for(suffix: str) -> int:
    """Return the byte limit for one upload.

    Images are capped lower than text documents: OCR rendering in memory and a 10 MiB
    screenshot is already far beyond what a policy page needs.
    """
    limit = _read_upload_limit()
    if suffix in IMAGE_SUFFIXES:
        return min(limit, IMAGE_MAX_BYTES)
    return limit


def _magic_ok(suffix: str, head: bytes) -> bool:
    """Return True when the first bytes match the declared container format."""
    if suffix == ".pdf":
        return head.startswith(b"%PDF-")
    if suffix in {".docx", ".pptx"}:
        return head.startswith(b"PK\x03\x04")
    if suffix == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    return True  # markdown/plain text is validated by decoding, not by magic


async def _read_limited(upload: UploadFile, *, limit: int, suffix: str) -> bytes:
    """Read at most ``limit`` bytes, rejecting oversize or non-text payloads."""
    chunks: list[bytes] = []
    total = 0
    head = b""
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        if not head:
            head = chunk[:8]
            if not _magic_ok(suffix, head):
                raise ToolError(
                    ErrorCode.UNSUPPORTED_FILE_TYPE, "文件实际格式与扩展名不符，已拒绝上传。"
                )
        total += len(chunk)
        if total > limit:
            raise ToolError(
                ErrorCode.FILE_TOO_LARGE,
                f"文件超过 {limit // (1024 * 1024)} MiB 上限。",
            )
        chunks.append(chunk)
    payload = b"".join(chunks)
    if not payload:
        raise ToolError(ErrorCode.VALIDATION_ERROR, "上传文件为空。")
    if suffix in {".md", ".markdown", ".txt"}:
        if b"\x00" in payload:
            raise ToolError(ErrorCode.UNSUPPORTED_FILE_TYPE, "文本文件包含二进制内容。")
        try:
            payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ToolError(ErrorCode.UNSUPPORTED_FILE_TYPE, "文本文件不是 UTF-8 编码。") from exc
    return payload


def _safe_suffix(filename: str) -> str:
    if not filename or _UNSAFE_NAME.search(filename):
        raise ToolError(ErrorCode.UNSAFE_FILE, "文件名不安全，已拒绝上传。")
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ToolError(
            ErrorCode.UNSUPPORTED_FILE_TYPE,
            "仅支持 PDF、DOCX、PPTX、Markdown、TXT、PNG、JPG。",
        )
    return suffix


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


async def _invalidate_faq_cache(request: Request, shop_id: UUID) -> None:
    """Best-effort FAQ cache invalidation after a chunk edit (contract §13)."""
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return
    from shopmate_ecommerce_assistant.rag.faq import FaqAnswerCache, RedisCacheBackend

    try:
        await FaqAnswerCache(RedisCacheBackend(redis)).invalidate_shop(str(shop_id))
    except Exception:
        logger.warning("FAQ cache invalidation failed after chunk edit")


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


def _parse_datetime(value: str, field: str) -> datetime:
    """Parse a UTC ISO 8601 form field, tolerating a trailing ``Z``."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolError(ErrorCode.VALIDATION_ERROR, f"{field} 不是合法的 ISO 8601 时间。") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _schedule_ingestion(request: Request, background: BackgroundTasks, version_id: UUID) -> bool:
    """Queue the ingestion worker when this process can load BGE-M3.

    A process whose RAG wiring failed (CI, unit tests, a machine without the weights)
    leaves the job ``queued`` rather than pretending to parse it; the job row is the
    durable record that a worker still has to pick up.
    """
    runner = getattr(request.app.state, "ingestion_runner", None)
    if runner is None:
        return False
    background.add_task(runner, version_id)
    return True


@router.post(
    "/documents",
    response_model=Envelope[UploadDocumentData],
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    request: Request,
    context: Admin,
    session: Annotated[AsyncSession, Depends(get_session)],
    background: BackgroundTasks,
    knowledge_base_id: Annotated[UUID, Form()],
    title: Annotated[str, Form(min_length=1, max_length=240)],
    doc_type: Annotated[str, Form()],
    locale: Annotated[str, Form()],
    region: Annotated[str, Form()],
    effective_from: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    effective_to: Annotated[str | None, Form()] = None,
) -> Envelope[UploadDocumentData]:
    """Validate an upload, store it under the controlled directory and queue a version."""
    repo = KnowledgeAdminRepository(session)
    knowledge_base = await repo.get_knowledge_base(shop_id=context.shop_id, kb_id=knowledge_base_id)
    if knowledge_base is None:
        raise ToolError(ErrorCode.VALIDATION_ERROR, "知识库不存在或不属于当前店铺。")
    if doc_type not in {item.value for item in KnowledgeDocType}:
        raise ToolError(ErrorCode.VALIDATION_ERROR, "doc_type 不在允许的取值内。")
    if not _LOCALE.match(locale) or not _REGION.match(region):
        raise ToolError(ErrorCode.VALIDATION_ERROR, "locale 或 region 格式不合法。")

    start = _parse_datetime(effective_from, "effective_from")
    end = None if not effective_to else _parse_datetime(effective_to, "effective_to")
    if end is not None and end <= start:
        raise ToolError(ErrorCode.VALIDATION_ERROR, "effective_to 必须晚于 effective_from。")

    suffix = _safe_suffix(file.filename or "")
    payload = await _read_limited(file, limit=_upload_limit_for(suffix), suffix=suffix)

    unique = uuid4().hex
    relative = f"uploads/{context.shop_id}/{unique}{suffix}"
    target = Path(paths.KNOWLEDGE_DIR) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)

    try:
        row = await repo.create_uploaded_document(
            shop_id=context.shop_id,
            knowledge_base=knowledge_base,
            document_key=f"upload-{unique}",
            title=title.strip(),
            doc_type=doc_type,
            locale=locale,
            region=region,
            effective_from=start,
            effective_to=end,
            source_uri=relative,
            filename=f"{unique}{suffix}",
            mime_type=SUPPORTED_SUFFIXES[suffix],
            content_hash=hashlib.sha256(payload).digest(),
            created_by=context.user_id,
        )
    except Exception:
        target.unlink(missing_ok=True)
        raise

    scheduled = _schedule_ingestion(request, background, row.version_id)
    request_id, trace_id = get_request_ids(request)
    await _audit(
        session,
        context=context,
        action="admin.document.upload",
        resource_type="knowledge_document",
        resource_id=row.document_id,
        request_id=request_id,
        trace_id=trace_id,
        metadata={
            "version_id": str(row.version_id),
            "doc_type": doc_type,
            "size_bytes": len(payload),
            "ingestion_scheduled": scheduled,
        },
    )
    return Envelope(
        data=UploadDocumentData(
            document_id=row.document_id,
            version_id=row.version_id,
            ingestion_job_id=row.ingestion_job_id,
            parse_status=row.parse_status,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.patch("/chunks/{chunk_id}", response_model=Envelope[ChunkPatchData])
async def patch_chunk(
    chunk_id: UUID,
    body: ChunkPatchRequest,
    request: Request,
    context: Admin,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[ChunkPatchData]:
    """Edit a chunk, recompute its hash, invalidate cache and demand a reindex."""
    repo = KnowledgeAdminRepository(session)
    row = await repo.edit_chunk(
        shop_id=context.shop_id,
        chunk_id=chunk_id,
        text=body.text,
        is_enabled=body.is_enabled,
        change_reason=body.change_reason,
    )
    if row is None:
        raise ToolError(ErrorCode.VALIDATION_ERROR, "未找到可编辑的知识单元。")
    await _invalidate_faq_cache(request, context.shop_id)
    request_id, trace_id = get_request_ids(request)
    await _audit(
        session,
        context=context,
        action="admin.chunk.update",
        resource_type="knowledge_chunk",
        resource_id=row.chunk_id,
        request_id=request_id,
        trace_id=trace_id,
        metadata={
            "version_id": str(row.version_id),
            "text_changed": body.text is not None,
            "is_enabled": row.is_enabled,
            "reindex_required": row.reindex_required,
        },
    )
    return Envelope(
        data=ChunkPatchData(
            chunk_id=row.chunk_id,
            version_id=row.version_id,
            text=row.text,
            is_enabled=row.is_enabled,
            content_hash=row.content_hash,
            reindex_required=row.reindex_required,
            updated_at=row.updated_at,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.delete("/chunks/{chunk_id}", response_model=Envelope[ChunkPatchData])
async def disable_chunk(
    chunk_id: UUID,
    request: Request,
    context: Admin,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[ChunkPatchData]:
    """Stop a chunk from being retrieved (soft delete) and demand a reindex."""
    repo = KnowledgeAdminRepository(session)
    row = await repo.soft_delete_chunk(shop_id=context.shop_id, chunk_id=chunk_id)
    if row is None:
        raise ToolError(ErrorCode.VALIDATION_ERROR, "未找到可停用的知识单元。")
    await _invalidate_faq_cache(request, context.shop_id)
    request_id, trace_id = get_request_ids(request)
    await _audit(
        session,
        context=context,
        action="admin.chunk.disable",
        resource_type="knowledge_chunk",
        resource_id=row.chunk_id,
        request_id=request_id,
        trace_id=trace_id,
        metadata={"version_id": str(row.version_id)},
    )
    return Envelope(
        data=ChunkPatchData(
            chunk_id=row.chunk_id,
            version_id=row.version_id,
            text=row.text,
            is_enabled=row.is_enabled,
            content_hash=row.content_hash,
            reindex_required=row.reindex_required,
            updated_at=row.updated_at,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post(
    "/documents/{document_id}/reindex",
    response_model=Envelope[ReindexData],
    status_code=status.HTTP_202_ACCEPTED,
)
async def reindex_document(
    document_id: UUID,
    request: Request,
    context: Admin,
    session: Annotated[AsyncSession, Depends(get_session)],
    background: BackgroundTasks,
) -> Envelope[ReindexData]:
    """Queue a fresh ingestion attempt for the document's current version."""
    repo = KnowledgeAdminRepository(session)
    document = await repo.get_document(shop_id=context.shop_id, document_id=document_id)
    if document is None:
        raise ToolError(ErrorCode.VALIDATION_ERROR, "未找到该文档。")
    if document.current_version_id is None:
        raise ToolError(ErrorCode.INVALID_STATE, "该文档还没有可重建的版本。")
    job_id = await repo.create_ingestion_job(
        shop_id=context.shop_id, version_id=document.current_version_id
    )
    if job_id is None:
        raise ToolError(ErrorCode.VALIDATION_ERROR, "未找到该文档的版本记录。")
    scheduled = _schedule_ingestion(request, background, document.current_version_id)
    request_id, trace_id = get_request_ids(request)
    await _audit(
        session,
        context=context,
        action="admin.document.reindex",
        resource_type="knowledge_document",
        resource_id=document_id,
        request_id=request_id,
        trace_id=trace_id,
        metadata={
            "version_id": str(document.current_version_id),
            "ingestion_job_id": str(job_id),
            "ingestion_scheduled": scheduled,
        },
    )
    return Envelope(
        data=ReindexData(ingestion_job_id=job_id, status="queued"),
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
