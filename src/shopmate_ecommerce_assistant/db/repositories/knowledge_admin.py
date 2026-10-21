"""Admin-scoped knowledge management reads and skeleton writes (stage 10).

Every statement filters on ``shop_id`` so an admin of one tenant can never list another
tenant's knowledge bases, documents, chunks or evaluation runs. Writes here are the
skeleton required by ``docs/06-api.md`` section 13: they persist metadata only; the
actual upload/parse/index pipeline remains the stage 5/7 ingestion path.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.core.ids import stable_uuid
from shopmate_ecommerce_assistant.db.models import (
    EvalRun,
    EvalRunStatus,
    IngestionJob,
    IngestionStatus,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeVersion,
    ParseStatus,
)
from shopmate_ecommerce_assistant.rag.chunking import estimate_token_count


@dataclass(frozen=True, slots=True)
class KnowledgeBaseRow:
    id: UUID
    name: str
    locale: str
    region: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DocumentRow:
    document_id: UUID
    title: str
    doc_type: str
    knowledge_base_id: UUID
    status: str
    locale: str
    region: str
    current_version_id: UUID | None
    current_version: str | None
    parse_status: str | None
    effective_from: datetime | None
    effective_to: datetime | None
    updated_at: datetime
    is_synthetic: bool


@dataclass(frozen=True, slots=True)
class ChunkRow:
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    chunk_index: int
    heading_path: tuple[str, ...]
    page_no: int | None
    text: str
    token_count: int
    is_enabled: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EvalRunRow:
    id: UUID
    dataset_name: str
    dataset_version: str
    status: str
    metrics: dict[str, Any]
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ChunkEditRow:
    """Result of an in-place chunk edit or soft delete (contract §13)."""

    chunk_id: UUID
    version_id: UUID
    text: str
    is_enabled: bool
    content_hash: str
    reindex_required: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UploadedDocumentRow:
    """The three ids returned by ``POST /admin/documents`` (202, pending)."""

    document_id: UUID
    version_id: UUID
    ingestion_job_id: UUID
    parse_status: str


@dataclass(frozen=True, slots=True)
class IngestTarget:
    """Everything the ingestion worker needs to re-parse one stored version."""

    shop_id: UUID
    knowledge_base_id: UUID
    knowledge_base_name: str
    document_id: UUID
    version_id: UUID
    job_id: UUID
    title: str
    doc_type: str
    version: str
    locale: str
    region: str
    effective_from: datetime
    effective_to: datetime | None
    source_uri: str


class KnowledgeAdminRepository:
    """Shop-scoped reads and metadata writes for the admin knowledge API."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- knowledge bases --------------------------------------------------
    async def list_knowledge_bases(self, *, shop_id: UUID) -> tuple[KnowledgeBaseRow, ...]:
        stmt = (
            sa.select(KnowledgeBase)
            .where(KnowledgeBase.shop_id == shop_id)
            .order_by(KnowledgeBase.created_at, KnowledgeBase.id)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return tuple(
            KnowledgeBaseRow(
                id=row.id,
                name=row.name,
                locale=row.locale,
                region=row.region,
                status=str(row.status),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        )

    async def create_knowledge_base(
        self, *, shop_id: UUID, name: str, locale: str, region: str
    ) -> KnowledgeBaseRow:
        row = KnowledgeBase(shop_id=shop_id, name=name, locale=locale, region=region)
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return KnowledgeBaseRow(
            id=row.id,
            name=row.name,
            locale=row.locale,
            region=row.region,
            status=str(row.status),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def get_knowledge_base(self, *, shop_id: UUID, kb_id: UUID) -> KnowledgeBaseRow | None:
        row = (
            await self._session.execute(
                sa.select(KnowledgeBase).where(
                    KnowledgeBase.shop_id == shop_id, KnowledgeBase.id == kb_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return KnowledgeBaseRow(
            id=row.id,
            name=row.name,
            locale=row.locale,
            region=row.region,
            status=str(row.status),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    # -- documents --------------------------------------------------------
    async def list_documents(
        self, *, shop_id: UUID, knowledge_base_id: UUID | None = None, limit: int = 50
    ) -> tuple[DocumentRow, ...]:
        stmt = (
            sa.select(
                KnowledgeDocument,
                KnowledgeVersion.version,
                KnowledgeVersion.parse_status,
                KnowledgeVersion.effective_from,
                KnowledgeVersion.effective_to,
            )
            .outerjoin(
                KnowledgeVersion,
                sa.and_(
                    KnowledgeVersion.id == KnowledgeDocument.current_version_id,
                    KnowledgeVersion.shop_id == KnowledgeDocument.shop_id,
                ),
            )
            .where(KnowledgeDocument.shop_id == shop_id, KnowledgeDocument.deleted_at.is_(None))
            .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id)
            .limit(limit)
        )
        if knowledge_base_id is not None:
            stmt = stmt.where(KnowledgeDocument.knowledge_base_id == knowledge_base_id)
        rows = (await self._session.execute(stmt)).all()
        return tuple(self._doc_from_row(row) for row in rows)

    async def get_document(self, *, shop_id: UUID, document_id: UUID) -> DocumentRow | None:
        stmt = (
            sa.select(
                KnowledgeDocument,
                KnowledgeVersion.version,
                KnowledgeVersion.parse_status,
                KnowledgeVersion.effective_from,
                KnowledgeVersion.effective_to,
            )
            .outerjoin(
                KnowledgeVersion,
                sa.and_(
                    KnowledgeVersion.id == KnowledgeDocument.current_version_id,
                    KnowledgeVersion.shop_id == KnowledgeDocument.shop_id,
                ),
            )
            .where(
                KnowledgeDocument.shop_id == shop_id,
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.deleted_at.is_(None),
            )
        )
        row = (await self._session.execute(stmt)).first()
        return None if row is None else self._doc_from_row(row)

    @staticmethod
    def _doc_from_row(row: Any) -> DocumentRow:
        doc = row[0]
        return DocumentRow(
            document_id=doc.id,
            title=doc.title,
            doc_type=str(doc.doc_type),
            knowledge_base_id=doc.knowledge_base_id,
            status=str(doc.status),
            locale=doc.locale,
            region=doc.region,
            current_version_id=doc.current_version_id,
            current_version=row[1],
            parse_status=None if row[2] is None else str(row[2]),
            effective_from=row[3],
            effective_to=row[4],
            updated_at=doc.updated_at,
            is_synthetic=bool(doc.is_synthetic),
        )

    # -- chunks -----------------------------------------------------------
    async def list_chunks(
        self,
        *,
        shop_id: UUID,
        document_id: UUID | None = None,
        version_id: UUID | None = None,
        limit: int = 50,
    ) -> tuple[ChunkRow, ...]:
        stmt = (
            sa.select(KnowledgeChunk)
            .where(KnowledgeChunk.shop_id == shop_id, KnowledgeChunk.deleted_at.is_(None))
            .order_by(KnowledgeChunk.chunk_index, KnowledgeChunk.id)
            .limit(limit)
        )
        if document_id is not None:
            stmt = stmt.where(KnowledgeChunk.document_id == document_id)
        if version_id is not None:
            stmt = stmt.where(KnowledgeChunk.version_id == version_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return tuple(
            ChunkRow(
                chunk_id=row.id,
                document_id=row.document_id,
                version_id=row.version_id,
                chunk_index=row.chunk_index,
                heading_path=tuple(str(part) for part in (row.heading_path or [])),
                page_no=row.page_no,
                text=row.text,
                token_count=int(row.token_count or 0),
                is_enabled=bool(row.is_enabled),
                updated_at=row.updated_at,
            )
            for row in rows
        )

    # -- evaluation runs --------------------------------------------------
    async def list_eval_runs(self, *, shop_id: UUID, limit: int = 50) -> tuple[EvalRunRow, ...]:
        stmt = (
            sa.select(EvalRun)
            .where(EvalRun.shop_id == shop_id)
            .order_by(EvalRun.created_at.desc(), EvalRun.id)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return tuple(
            EvalRunRow(
                id=row.id,
                dataset_name=row.dataset_name,
                dataset_version=row.dataset_version,
                status=str(row.status),
                metrics=row.metrics_jsonb if isinstance(row.metrics_jsonb, dict) else {},
                created_by=row.created_by,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        )

    async def create_eval_run(
        self,
        *,
        shop_id: UUID,
        dataset_name: str,
        dataset_version: str,
        config: dict[str, Any],
        created_by: UUID | None,
    ) -> EvalRunRow:
        row = EvalRun(
            shop_id=shop_id,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            config_jsonb=config,
            status=EvalRunStatus.QUEUED,
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return EvalRunRow(
            id=row.id,
            dataset_name=row.dataset_name,
            dataset_version=row.dataset_version,
            status=str(row.status),
            metrics={},
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    # -- upload -----------------------------------------------------------
    async def create_uploaded_document(
        self,
        *,
        shop_id: UUID,
        knowledge_base: KnowledgeBaseRow,
        document_key: str,
        title: str,
        doc_type: str,
        locale: str,
        region: str,
        effective_from: datetime,
        effective_to: datetime | None,
        source_uri: str,
        filename: str,
        mime_type: str,
        content_hash: bytes,
        created_by: UUID | None,
        version: str = "1",
    ) -> UploadedDocumentRow:
        """Create document + pending version + queued ingestion job for one upload.

        Ids follow the same derivation as :func:`rag.ingest.pipeline.ingest_source`, so the
        worker re-parses *this* version instead of creating a parallel document.
        """
        document_id = stable_uuid("document", str(shop_id), knowledge_base.name, document_key)
        version_id = stable_uuid("version", str(document_id), version)
        job_id = stable_uuid("ingestion_job", str(version_id), "1")

        # Staged flushes: composite FKs are declared without ORM relationships, so the
        # insert order (document -> version -> job) is made explicit here.
        self._session.add(
            KnowledgeDocument(
                id=document_id,
                shop_id=shop_id,
                knowledge_base_id=knowledge_base.id,
                title=title,
                doc_type=doc_type,
                locale=locale,
                region=region,
                status=KnowledgeDocumentStatus.ACTIVE,
                is_synthetic=True,
            )
        )
        await self._session.flush()
        self._session.add(
            KnowledgeVersion(
                id=version_id,
                shop_id=shop_id,
                document_id=document_id,
                version=version,
                source_uri=source_uri,
                source_filename=filename,
                mime_type=mime_type,
                content_hash=content_hash,
                effective_from=effective_from,
                effective_to=effective_to,
                parse_status=ParseStatus.PENDING,
                created_by=created_by,
            )
        )
        await self._session.flush()
        self._session.add(
            IngestionJob(
                id=job_id,
                shop_id=shop_id,
                version_id=version_id,
                status=IngestionStatus.QUEUED,
                attempt_count=1,
            )
        )
        await self._session.execute(
            sa.update(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .values(current_version_id=version_id, updated_at=sa.func.now())
        )
        await self._session.commit()
        return UploadedDocumentRow(
            document_id=document_id,
            version_id=version_id,
            ingestion_job_id=job_id,
            parse_status=ParseStatus.PENDING.value,
        )

    # -- chunk writes -----------------------------------------------------
    async def get_chunk(self, *, shop_id: UUID, chunk_id: UUID) -> KnowledgeChunk | None:
        return (
            await self._session.execute(
                sa.select(KnowledgeChunk).where(
                    KnowledgeChunk.shop_id == shop_id,
                    KnowledgeChunk.id == chunk_id,
                    KnowledgeChunk.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def edit_chunk(
        self,
        *,
        shop_id: UUID,
        chunk_id: UUID,
        text: str | None,
        is_enabled: bool | None,
        change_reason: str | None,
    ) -> ChunkEditRow | None:
        """Apply an edit, recompute ``content_hash`` and mark the index stale.

        The historical text is not overwritten in place on the version: a version's
        chunks are the audit record, so the edit records ``metadata_jsonb.index`` instead
        of silently replacing history, and returns ``reindex_required=True`` so the
        caller knows the vector index no longer matches PostgreSQL.
        """
        chunk = await self.get_chunk(shop_id=shop_id, chunk_id=chunk_id)
        if chunk is None:
            return None
        metadata = dict(chunk.metadata_jsonb) if isinstance(chunk.metadata_jsonb, dict) else {}
        values: dict[str, Any] = {"updated_at": sa.func.now()}
        if text is not None:
            values["text"] = text
            values["content_hash"] = hashlib.sha256(text.encode("utf-8")).digest()
            values["token_count"] = estimate_token_count(text)
        if is_enabled is not None:
            values["is_enabled"] = is_enabled
        metadata["index"] = {
            "stale": True,
            "reason": "chunk_edited",
            "at": datetime.now(UTC).isoformat(),
            "change_reason": change_reason,
        }
        values["metadata_jsonb"] = metadata
        await self._session.execute(
            sa.update(KnowledgeChunk)
            .where(KnowledgeChunk.shop_id == shop_id, KnowledgeChunk.id == chunk_id)
            .values(**values)
        )
        await self._session.commit()
        refreshed = await self.get_chunk(shop_id=shop_id, chunk_id=chunk_id)
        assert refreshed is not None  # the row was just updated in this transaction
        return _chunk_edit_row(refreshed, reindex_required=True)

    async def soft_delete_chunk(
        self, *, shop_id: UUID, chunk_id: UUID
    ) -> ChunkEditRow | None:
        """Stop a chunk from being retrieved without deleting its audit row."""
        chunk = await self.get_chunk(shop_id=shop_id, chunk_id=chunk_id)
        if chunk is None:
            return None
        await self._session.execute(
            sa.update(KnowledgeChunk)
            .where(KnowledgeChunk.shop_id == shop_id, KnowledgeChunk.id == chunk_id)
            .values(is_enabled=False, deleted_at=sa.func.now(), updated_at=sa.func.now())
        )
        await self._session.commit()
        refreshed = (
            await self._session.execute(
                sa.select(KnowledgeChunk).where(
                    KnowledgeChunk.shop_id == shop_id, KnowledgeChunk.id == chunk_id
                )
            )
        ).scalar_one_or_none()
        row = refreshed if refreshed is not None else chunk
        return _chunk_edit_row(row, reindex_required=True)

    # -- reindex ----------------------------------------------------------
    async def create_ingestion_job(
        self, *, shop_id: UUID, version_id: UUID
    ) -> UUID | None:
        """Queue a new ingestion attempt for ``version_id`` and mark it pending."""
        version = (
            await self._session.execute(
                sa.select(KnowledgeVersion).where(
                    KnowledgeVersion.shop_id == shop_id, KnowledgeVersion.id == version_id
                )
            )
        ).scalar_one_or_none()
        if version is None:
            return None
        total = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(IngestionJob)
            .where(IngestionJob.version_id == version_id)
        )
        attempt = int(total or 0) + 1
        job_id = stable_uuid("ingestion_job", str(version_id), str(attempt))
        self._session.add(
            IngestionJob(
                id=job_id,
                shop_id=shop_id,
                version_id=version_id,
                status=IngestionStatus.QUEUED,
                attempt_count=attempt,
            )
        )
        await self._session.execute(
            sa.update(KnowledgeVersion)
            .where(KnowledgeVersion.id == version_id)
            .values(parse_status=ParseStatus.PENDING.value, updated_at=sa.func.now())
        )
        await self._session.commit()
        return job_id

    async def latest_queued_job_id(self, *, shop_id: UUID, version_id: UUID) -> UUID | None:
        return await self._session.scalar(
            sa.select(IngestionJob.id)
            .where(
                IngestionJob.shop_id == shop_id,
                IngestionJob.version_id == version_id,
                IngestionJob.status == IngestionStatus.QUEUED,
            )
            .order_by(IngestionJob.attempt_count.desc())
            .limit(1)
        )

    async def load_ingest_target(self, *, version_id: UUID) -> IngestTarget | None:
        """Load the version/document/knowledge-base triple needed by the ingest worker."""
        row = (
            await self._session.execute(
                sa.select(KnowledgeVersion, KnowledgeDocument, KnowledgeBase)
                .join(
                    KnowledgeDocument,
                    sa.and_(
                        KnowledgeDocument.shop_id == KnowledgeVersion.shop_id,
                        KnowledgeDocument.id == KnowledgeVersion.document_id,
                    ),
                )
                .join(
                    KnowledgeBase,
                    sa.and_(
                        KnowledgeBase.shop_id == KnowledgeDocument.shop_id,
                        KnowledgeBase.id == KnowledgeDocument.knowledge_base_id,
                    ),
                )
                .where(KnowledgeVersion.id == version_id)
            )
        ).first()
        if row is None:
            return None
        version, document, knowledge_base = row
        job_id = await self.latest_queued_job_id(
            shop_id=version.shop_id, version_id=version.id
        )
        if job_id is None:
            job_id = stable_uuid("ingestion_job", str(version.id), "1")
        return IngestTarget(
            shop_id=version.shop_id,
            knowledge_base_id=knowledge_base.id,
            knowledge_base_name=knowledge_base.name,
            document_id=document.id,
            version_id=version.id,
            job_id=job_id,
            title=document.title,
            doc_type=str(document.doc_type),
            version=version.version,
            locale=document.locale,
            region=document.region,
            effective_from=version.effective_from,
            effective_to=version.effective_to,
            source_uri=version.source_uri,
        )


def _chunk_edit_row(chunk: KnowledgeChunk, *, reindex_required: bool) -> ChunkEditRow:
    return ChunkEditRow(
        chunk_id=chunk.id,
        version_id=chunk.version_id,
        text=chunk.text,
        is_enabled=bool(chunk.is_enabled),
        content_hash=bytes(chunk.content_hash).hex(),
        reindex_required=reindex_required,
        updated_at=chunk.updated_at,
    )


__all__ = [
    "ChunkEditRow",
    "ChunkRow",
    "DocumentRow",
    "EvalRunRow",
    "IngestTarget",
    "KnowledgeAdminRepository",
    "KnowledgeBaseRow",
    "UploadedDocumentRow",
]
