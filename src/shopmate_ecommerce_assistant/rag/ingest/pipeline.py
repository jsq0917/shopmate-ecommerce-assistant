"""Durable knowledge ingestion pipeline: parse -> chunk -> embed -> Milvus -> PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.ids import stable_uuid
from shopmate_ecommerce_assistant.db.models import (
    IngestionJob,
    IngestionStatus,
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeVersion,
    ParseStatus,
)
from shopmate_ecommerce_assistant.rag.chunking import (
    ChunkDraft,
    estimate_token_count,
    split_parent_child,
)
from shopmate_ecommerce_assistant.rag.embeddings import HybridEmbeddingProvider
from shopmate_ecommerce_assistant.rag.errors import (
    DocumentTooLarge,
    EmptyDocument,
    IngestionError,
    InvalidEmbeddingError,
)
from shopmate_ecommerce_assistant.rag.ingest.loaders import SUPPORTED_SUFFIXES, load_document
from shopmate_ecommerce_assistant.rag.ingest.manifest import SourceSpec
from shopmate_ecommerce_assistant.rag.milvus_store import ChunkVector, MilvusKnowledgeStore

logger = logging.getLogger(__name__)

EMPTY_DIGEST = hashlib.sha256(b"").digest()
SAFE_MESSAGE_LIMIT = 500


@dataclass(slots=True)
class IngestOutcome:
    """Result of one ingestion attempt; failures are reported, not raised."""

    document_id: UUID
    version_id: UUID
    job_id: UUID
    status: str
    chunk_count: int = 0
    parent_count: int = 0
    child_count: int = 0
    milvus_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    embedding_model: str | None = None
    embedding_fingerprint: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == ParseStatus.READY.value


def _content_hash(payload: bytes) -> bytes:
    return hashlib.sha256(payload).digest()


def _safe_source_uri(raw: str) -> str:
    """Normalise a manifest path for storage without trusting it as a filesystem path."""
    parts = [
        part
        for part in PurePosixPath(raw.replace("\\", "/")).parts
        if part not in {"", ".", "..", "/"}
    ]
    return PurePosixPath(*parts).as_posix() if parts else "unknown"


def _classify(exc: Exception) -> tuple[str, str, bool]:
    if isinstance(exc, InvalidEmbeddingError):
        return exc.code, exc.message, exc.retryable
    if isinstance(exc, IngestionError):
        # Vector store outages and model load failures are worth retrying; a parse
        # failure or an unsafe path is not.
        retryable = exc.code in {
            "VECTOR_STORE_UNAVAILABLE",
            "EMBEDDING_MODEL_UNAVAILABLE",
            "COLLECTION_SCHEMA_MISMATCH",
        }
        return exc.code, exc.message, retryable
    if isinstance(exc, FileNotFoundError):
        return "FILE_NOT_FOUND", "文档不存在或不可读", True
    logger.exception("unexpected ingestion failure")
    return "UNEXPECTED_ERROR", "文档入库时发生未预期错误", False


async def _upsert_knowledge_base(
    session: AsyncSession, *, shop_id: UUID, name: str, locale: str, region: str
) -> UUID:
    kb_id = stable_uuid("knowledge_base", str(shop_id), name)
    stmt = (
        postgresql.insert(KnowledgeBase)
        .values(
            id=kb_id,
            shop_id=shop_id,
            name=name,
            locale=locale,
            region=region,
            status=KnowledgeBaseStatus.ACTIVE.value,
        )
        .on_conflict_do_update(
            index_elements=[KnowledgeBase.id],
            set_={
                "locale": locale,
                "region": region,
                "status": KnowledgeBaseStatus.ACTIVE.value,
                "updated_at": sa.func.now(),
            },
        )
    )
    await session.execute(stmt)
    return kb_id


async def _upsert_document(
    session: AsyncSession,
    *,
    document_id: UUID,
    shop_id: UUID,
    kb_id: UUID,
    spec: SourceSpec,
) -> None:
    stmt = (
        postgresql.insert(KnowledgeDocument)
        .values(
            id=document_id,
            shop_id=shop_id,
            knowledge_base_id=kb_id,
            title=spec.title,
            doc_type=spec.doc_type,
            locale=spec.locale,
            region=spec.region,
            status=KnowledgeDocumentStatus.ACTIVE.value,
            is_synthetic=True,
        )
        .on_conflict_do_update(
            index_elements=[KnowledgeDocument.id],
            set_={
                "title": spec.title,
                "doc_type": spec.doc_type,
                "locale": spec.locale,
                "region": spec.region,
                "status": KnowledgeDocumentStatus.ACTIVE.value,
                "deleted_at": None,
                "updated_at": sa.func.now(),
            },
        )
    )
    await session.execute(stmt)


async def _upsert_version(
    session: AsyncSession,
    *,
    version_id: UUID,
    document_id: UUID,
    shop_id: UUID,
    spec: SourceSpec,
    source_uri: str,
    filename: str,
    mime_type: str,
    digest: bytes,
    parse_status: ParseStatus,
    created_by: UUID | None,
) -> None:
    stmt = (
        postgresql.insert(KnowledgeVersion)
        .values(
            id=version_id,
            shop_id=shop_id,
            document_id=document_id,
            version=spec.version,
            source_uri=source_uri,
            source_filename=filename,
            mime_type=mime_type,
            content_hash=digest,
            effective_from=spec.effective_from,
            effective_to=spec.effective_to,
            parse_status=parse_status.value,
            created_by=created_by,
        )
        .on_conflict_do_update(
            index_elements=[
                KnowledgeVersion.shop_id,
                KnowledgeVersion.document_id,
                KnowledgeVersion.version,
            ],
            set_={
                "source_uri": source_uri,
                "source_filename": filename,
                "mime_type": mime_type,
                "content_hash": digest,
                "effective_from": spec.effective_from,
                "effective_to": spec.effective_to,
                "parse_status": parse_status.value,
                "failure_code": None,
                "failure_message_safe": None,
                "updated_at": sa.func.now(),
            },
        )
    )
    await session.execute(stmt)


async def _next_attempt(session: AsyncSession, version_id: UUID) -> int:
    total = await session.scalar(
        sa.select(sa.func.count())
        .select_from(IngestionJob)
        .where(IngestionJob.version_id == version_id)
    )
    return int(total or 0) + 1


def _chunk_rows(
    drafts: list[ChunkDraft],
    *,
    version_id: UUID,
    shop_id: UUID,
    kb_id: UUID,
    document_id: UUID,
    spec: SourceSpec,
    digest: str,
    embedding_meta: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[ChunkDraft], list[str]]:
    """Build ORM-ready chunk rows plus the child drafts and their ids."""
    ids: dict[int, UUID] = {
        draft.chunk_index: stable_uuid("chunk", str(version_id), str(draft.chunk_index))
        for draft in drafts
    }
    rows: list[dict[str, Any]] = []
    children: list[ChunkDraft] = []
    child_ids: list[str] = []
    for draft in drafts:
        parent_id = None if draft.parent_index is None else ids[draft.parent_index]
        rows.append(
            {
                "id": ids[draft.chunk_index],
                "shop_id": shop_id,
                "knowledge_base_id": kb_id,
                "document_id": document_id,
                "version_id": version_id,
                "parent_id": parent_id,
                "chunk_index": draft.chunk_index,
                "heading_path": list(draft.heading_path),
                "page_no": draft.page_no,
                "text": draft.text,
                "content_hash": _content_hash(draft.text.encode("utf-8")),
                "token_count": estimate_token_count(draft.text),
                "is_enabled": draft.role == "child",
                "metadata_jsonb": {
                    "role": draft.role,
                    "version": spec.version,
                    "doc_type": spec.doc_type,
                    "is_synthetic": True,
                    "source_digest": digest,
                    # Stage 7 contract: every chunk records which weights produced its
                    # vector, so a re-import can be compared against the index.
                    # Parent chunks are not embedded; ``embedded`` states that explicitly.
                    "embedding": {**embedding_meta, "embedded": draft.role == "child"},
                },
            }
        )
        if draft.role == "child":
            children.append(draft)
            child_ids.append(str(ids[draft.chunk_index]))
    return rows, children, child_ids


async def ingest_source(
    *,
    session: AsyncSession,
    settings: Settings,
    store: MilvusKnowledgeStore | None,
    embedder: HybridEmbeddingProvider,
    spec: SourceSpec,
    base_dir: Path,
    shop_id: UUID,
    created_by: UUID | None = None,
    milvus_enabled: bool = True,
    knowledge_base_id: UUID | None = None,
    document_id: UUID | None = None,
    version_id: UUID | None = None,
    job_id: UUID | None = None,
) -> IngestOutcome:
    """Ingest one document version and record an auditable job.

    Metadata rows are written before the file is read, so a missing or corrupt file still
    leaves an explicit ``failed`` version with a safe error code. Failures are recorded
    instead of raised so one bad document cannot abort a batch run.

    ``knowledge_base_id`` / ``document_id`` / ``version_id`` / ``job_id`` let the admin
    upload path re-parse **the rows it already created** (a knowledge base created through
    ``POST /admin/knowledge-bases`` has a random id, not the manifest's stable id) instead
    of creating a parallel document. All four default to ``None``, which keeps the CLI
    manifest behaviour byte-identical to stage 5/7.
    """
    source_uri = _safe_source_uri(spec.file)
    filename = PurePosixPath(source_uri).name or "unknown"
    mime_type = SUPPORTED_SUFFIXES.get(Path(filename).suffix.lower(), "application/octet-stream")
    if knowledge_base_id is not None:
        kb_id = knowledge_base_id
    else:
        kb_id = stable_uuid("knowledge_base", str(shop_id), spec.knowledge_base)
    document_id = document_id or stable_uuid(
        "document", str(shop_id), spec.knowledge_base, spec.document_key
    )
    version_id = version_id or stable_uuid("version", str(document_id), spec.version)
    job_id_explicit = job_id is not None
    job_id = job_id or stable_uuid("ingestion_job", str(version_id), "pending")
    parent_count = 0
    child_count = 0
    milvus_count = 0

    try:
        if knowledge_base_id is None:
            kb_id = await _upsert_knowledge_base(
                session,
                shop_id=shop_id,
                name=spec.knowledge_base,
                locale=spec.locale,
                region=spec.region,
            )
        await _upsert_document(
            session, document_id=document_id, shop_id=shop_id, kb_id=kb_id, spec=spec
        )
        await _upsert_version(
            session,
            version_id=version_id,
            document_id=document_id,
            shop_id=shop_id,
            spec=spec,
            source_uri=source_uri,
            filename=filename,
            mime_type=mime_type,
            digest=EMPTY_DIGEST,
            parse_status=ParseStatus.PROCESSING,
            created_by=created_by,
        )
        reuse_job = job_id if job_id_explicit else None
        if reuse_job is None:
            attempt = await _next_attempt(session, version_id)
            job_id = stable_uuid("ingestion_job", str(version_id), str(attempt))
            session.add(
                IngestionJob(
                    id=job_id,
                    shop_id=shop_id,
                    version_id=version_id,
                    status=IngestionStatus.RUNNING.value,
                    attempt_count=attempt,
                    started_at=datetime.now(UTC),
                )
            )
        else:
            # The admin upload already queued this attempt; mark it running in place so one
            # HTTP upload maps to exactly one job row.
            await session.execute(
                sa.update(IngestionJob)
                .where(IngestionJob.id == reuse_job)
                .values(
                    status=IngestionStatus.RUNNING.value,
                    started_at=datetime.now(UTC),
                    updated_at=sa.func.now(),
                )
            )
        await session.commit()

        # Resolve inside the guard so a path that escapes the knowledge directory is
        # recorded as a failed version instead of aborting the whole batch.
        path = spec.resolve(base_dir)

        if not path.is_file():
            raise FileNotFoundError(path.name)
        size = path.stat().st_size
        if size > settings.knowledge_upload_max_bytes:
            raise DocumentTooLarge(size, settings.knowledge_upload_max_bytes)

        payload = path.read_bytes()
        digest = _content_hash(payload)
        await session.execute(
            sa.update(KnowledgeVersion)
            .where(KnowledgeVersion.id == version_id)
            .values(content_hash=digest, updated_at=sa.func.now())
        )
        await session.commit()

        loaded = load_document(path)
        drafts = split_parent_child(
            loaded.blocks,
            parent_chars=settings.parent_chunk_chars,
            child_chars=settings.child_chunk_chars,
        )
        if not drafts:
            raise EmptyDocument()

        embedding_meta = embedder.metadata.as_dict()
        rows, children, child_ids = _chunk_rows(
            drafts,
            version_id=version_id,
            shop_id=shop_id,
            kb_id=kb_id,
            document_id=document_id,
            spec=spec,
            digest=digest.hex(),
            embedding_meta=embedding_meta,
        )
        if not children:
            raise EmptyDocument()

        # One forward pass per batch yields both dense and sparse vectors. Any NaN/Inf or
        # missing sparse vector raises here, so the whole version fails before a single
        # row reaches PostgreSQL or Milvus — no partial, silently broken index.
        vectors = embedder.embed_documents_hybrid(
            [f"{spec.title}\n{'/'.join(draft.heading_path)}\n{draft.text}" for draft in children]
        )
        if len(vectors) != len(children):
            raise InvalidEmbeddingError(
                "EMBEDDING_OUTPUT_LENGTH", "向量数量与子块数量不一致，本批已拒绝写入"
            )
        parent_count = len(drafts) - len(children)
        child_count = len(children)

        await session.execute(
            sa.delete(KnowledgeChunk).where(KnowledgeChunk.version_id == version_id)
        )
        await session.execute(postgresql.insert(KnowledgeChunk).values(rows))

        if milvus_enabled and store is not None:
            store.delete_version(str(version_id))
            store.upsert_chunks(
                [
                    ChunkVector(
                        chunk_id=child_ids[index],
                        shop_id=str(shop_id),
                        knowledge_base_id=str(kb_id),
                        document_id=str(document_id),
                        version_id=str(version_id),
                        doc_type=spec.doc_type,
                        locale=spec.locale,
                        region=spec.region,
                        status=ParseStatus.READY.value,
                        effective_from=spec.effective_from,
                        effective_to=spec.effective_to,
                        page_no=draft.page_no,
                        heading_path=draft.heading_path,
                        text=draft.text,
                        metadata_json=json.dumps(
                            {
                                "document_key": spec.document_key,
                                "version": spec.version,
                                "chunk_role": "child",
                                "is_synthetic": True,
                                "embedding": embedding_meta,
                            },
                            ensure_ascii=False,
                        ),
                        dense=vector.dense,
                        sparse=vector.sparse,
                        # Fixed provider tag (schema contract); the full model name and
                        # weight fingerprint live in metadata_json / metadata_jsonb.
                        embedding_model=str(embedding_meta["provider"]),
                    )
                    for index, (draft, vector) in enumerate(zip(children, vectors, strict=True))
                ]
            )
            milvus_count = len(children)

        await session.execute(
            sa.update(KnowledgeVersion)
            .where(KnowledgeVersion.id == version_id)
            .values(
                parse_status=ParseStatus.READY.value,
                failure_code=None,
                failure_message_safe=None,
                updated_at=sa.func.now(),
            )
        )
        await session.execute(
            sa.update(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .values(current_version_id=version_id, updated_at=sa.func.now())
        )
        await session.execute(
            sa.update(IngestionJob)
            .where(IngestionJob.id == job_id)
            .values(
                status=IngestionStatus.SUCCEEDED.value,
                finished_at=datetime.now(UTC),
                error_code=None,
                error_message_safe=None,
                updated_at=sa.func.now(),
            )
        )
        await session.commit()
        logger.info(
            "ingested knowledge version",
            extra={
                "document_id": str(document_id),
                "version_id": str(version_id),
                "children": child_count,
                "parents": parent_count,
            },
        )
        return IngestOutcome(
            document_id=document_id,
            version_id=version_id,
            job_id=job_id,
            status=ParseStatus.READY.value,
            chunk_count=len(rows),
            parent_count=parent_count,
            child_count=child_count,
            milvus_count=milvus_count,
            embedding_model=str(embedding_meta["model"]),
            embedding_fingerprint=str(embedding_meta["fingerprint"]),
        )
    except Exception as exc:  # noqa: BLE001 - the failure is recorded, not swallowed
        await session.rollback()
        code, message, retryable = _classify(exc)
        if store is not None and milvus_enabled:
            try:
                store.delete_version(str(version_id))
            except IngestionError:
                logger.warning("failed to clear vectors for %s", version_id)
        await _record_failure(
            session,
            version_id=version_id,
            job_id=job_id,
            code=code,
            message=message,
        )
        return IngestOutcome(
            document_id=document_id,
            version_id=version_id,
            job_id=job_id,
            status=ParseStatus.FAILED.value,
            parent_count=parent_count,
            child_count=child_count,
            milvus_count=milvus_count,
            error_code=code,
            error_message=message,
            retryable=retryable,
        )


async def _record_failure(
    session: AsyncSession,
    *,
    version_id: UUID,
    job_id: UUID,
    code: str,
    message: str,
) -> None:
    """Persist failure state and remove any partially stored chunks."""
    safe_message = message[:SAFE_MESSAGE_LIMIT]
    try:
        await session.execute(
            sa.delete(KnowledgeChunk).where(KnowledgeChunk.version_id == version_id)
        )
        await session.execute(
            sa.update(KnowledgeVersion)
            .where(KnowledgeVersion.id == version_id)
            .values(
                parse_status=ParseStatus.FAILED.value,
                failure_code=code,
                failure_message_safe=safe_message,
                updated_at=sa.func.now(),
            )
        )
        updated = await session.execute(
            sa.update(IngestionJob)
            .where(IngestionJob.id == job_id)
            .values(
                status=IngestionStatus.FAILED.value,
                error_code=code,
                error_message_safe=safe_message,
                finished_at=datetime.now(UTC),
                updated_at=sa.func.now(),
            )
        )
        if updated.rowcount == 0:
            logger.warning("ingestion job %s missing while recording failure", job_id)
        await session.commit()
    except Exception:  # pragma: no cover - reporting must never raise
        await session.rollback()
        logger.exception("failed to record ingestion failure for %s", version_id)
