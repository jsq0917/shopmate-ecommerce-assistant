"""Admin-scoped knowledge management reads and skeleton writes (stage 10).

Every statement filters on ``shop_id`` so an admin of one tenant can never list another
tenant's knowledge bases, documents, chunks or evaluation runs. Writes here are the
skeleton required by ``docs/06-api.md`` section 13: they persist metadata only; the
actual upload/parse/index pipeline remains the stage 5/7 ingestion path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.db.models import (
    EvalRun,
    EvalRunStatus,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
)


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


__all__ = [
    "ChunkRow",
    "DocumentRow",
    "EvalRunRow",
    "KnowledgeAdminRepository",
    "KnowledgeBaseRow",
]
