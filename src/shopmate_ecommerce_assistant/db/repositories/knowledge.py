"""Authoritative knowledge metadata reads for retrieval.

Milvus is a candidate generator, not a permission system. After fusion, every candidate
chunk is re-read from PostgreSQL together with its document and version so that expired
versions, disabled chunks, cross-shop rows and soft-deleted documents cannot appear in an
answer even if the vector index still holds them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.db.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
    ParseStatus,
)


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    """Joined metadata for one candidate chunk."""

    chunk_id: UUID
    shop_id: UUID
    knowledge_base_id: UUID
    document_id: UUID
    version_id: UUID
    parent_id: UUID | None
    chunk_index: int
    heading_path: tuple[str, ...]
    page_no: int | None
    text: str
    token_count: int
    is_enabled: bool
    deleted_at: datetime | None
    title: str
    doc_type: str
    locale: str
    region: str
    document_status: str
    document_deleted_at: datetime | None
    version: str
    effective_from: datetime
    effective_to: datetime | None
    parse_status: str
    metadata_jsonb: dict[str, Any]


def _to_metadata(row: Any) -> ChunkMetadata:
    data = row._mapping
    heading = data["heading_path"] or []
    return ChunkMetadata(
        chunk_id=data["id"],
        shop_id=data["shop_id"],
        knowledge_base_id=data["knowledge_base_id"],
        document_id=data["document_id"],
        version_id=data["version_id"],
        parent_id=data["parent_id"],
        chunk_index=data["chunk_index"],
        heading_path=tuple(str(part) for part in heading),
        page_no=data["page_no"],
        text=data["text"],
        token_count=int(data["token_count"] or 0),
        is_enabled=bool(data["is_enabled"]),
        deleted_at=data["deleted_at"],
        title=data["title"],
        doc_type=str(data["doc_type"]),
        locale=data["locale"],
        region=data["region"],
        document_status=str(data["document_status"]),
        document_deleted_at=data["document_deleted_at"],
        version=data["version"],
        effective_from=data["effective_from"],
        effective_to=data["effective_to"],
        parse_status=str(data["parse_status"]),
        metadata_jsonb=data["metadata_jsonb"] if isinstance(data["metadata_jsonb"], dict) else {},
    )


async def load_chunk_metadata(
    session: AsyncSession, chunk_ids: Sequence[UUID]
) -> dict[UUID, ChunkMetadata]:
    """Load chunk + document + version metadata for the given chunk ids."""
    if not chunk_ids:
        return {}
    stmt = (
        sa.select(
            KnowledgeChunk.id,
            KnowledgeChunk.shop_id,
            KnowledgeChunk.knowledge_base_id,
            KnowledgeChunk.document_id,
            KnowledgeChunk.version_id,
            KnowledgeChunk.parent_id,
            KnowledgeChunk.chunk_index,
            KnowledgeChunk.heading_path,
            KnowledgeChunk.page_no,
            KnowledgeChunk.text,
            KnowledgeChunk.token_count,
            KnowledgeChunk.is_enabled,
            KnowledgeChunk.deleted_at,
            KnowledgeChunk.metadata_jsonb,
            KnowledgeDocument.title,
            KnowledgeDocument.doc_type.label("doc_type"),
            KnowledgeDocument.locale,
            KnowledgeDocument.region,
            KnowledgeDocument.status.label("document_status"),
            KnowledgeDocument.deleted_at.label("document_deleted_at"),
            KnowledgeVersion.version,
            KnowledgeVersion.effective_from,
            KnowledgeVersion.effective_to,
            KnowledgeVersion.parse_status,
        )
        .join(
            KnowledgeDocument,
            sa.and_(
                KnowledgeDocument.id == KnowledgeChunk.document_id,
                KnowledgeDocument.shop_id == KnowledgeChunk.shop_id,
            ),
        )
        .join(
            KnowledgeVersion,
            sa.and_(
                KnowledgeVersion.id == KnowledgeChunk.version_id,
                KnowledgeVersion.shop_id == KnowledgeChunk.shop_id,
            ),
        )
        .where(KnowledgeChunk.id.in_(list(chunk_ids)))
    )
    rows = (await session.execute(stmt)).all()
    result: dict[UUID, ChunkMetadata] = {}
    for row in rows:
        meta = _to_metadata(row)
        result[meta.chunk_id] = meta
    return result


def authorization_issues(
    meta: ChunkMetadata,
    *,
    shop_id: UUID,
    knowledge_base_id: UUID | None,
    knowledge_base_ids: Collection[UUID] | None = None,
    locale: str | None,
    region: str | None,
    at: datetime,
    allowed_doc_types: Sequence[str] | None = None,
) -> list[str]:
    """Return the reasons a chunk must not be cited (empty list means authorised)."""
    issues: list[str] = []
    if meta.shop_id != shop_id:
        issues.append("cross_shop")
    if knowledge_base_ids and meta.knowledge_base_id not in knowledge_base_ids:
        issues.append("wrong_knowledge_base")
    elif not knowledge_base_ids and knowledge_base_id is not None:
        if meta.knowledge_base_id != knowledge_base_id:
            issues.append("wrong_knowledge_base")
    if meta.parse_status != ParseStatus.READY.value:
        issues.append("version_not_ready")
    if meta.document_deleted_at is not None:
        issues.append("document_deleted")
    if meta.document_status != "active":
        issues.append("document_inactive")
    if not meta.is_enabled:
        issues.append("chunk_disabled")
    if meta.deleted_at is not None:
        issues.append("chunk_deleted")
    if meta.effective_from > at:
        issues.append("not_yet_effective")
    if meta.effective_to is not None and meta.effective_to <= at:
        issues.append("expired")
    if region and meta.region != region:
        issues.append("wrong_region")
    if locale and meta.locale != locale:
        issues.append("wrong_locale")
    if allowed_doc_types and meta.doc_type not in allowed_doc_types:
        issues.append("wrong_doc_type")
    return issues


@dataclass(frozen=True, slots=True)
class KnowledgeVersionRow:
    """One document's current-version state, used to fingerprint the knowledge base."""

    document_id: str
    current_version_id: str | None
    version: str | None
    document_status: str
    document_updated_at: datetime | None
    effective_from: datetime | None
    effective_to: datetime | None
    parse_status: str | None


def version_digest_from_rows(
    rows: Iterable[KnowledgeVersionRow],
    *,
    chunk_updated_at: datetime | None = None,
    enabled_chunks: int = 0,
) -> str:
    """Fingerprint the effective knowledge state.

    Any new current version, status change, effective-window change, chunk edit/disable
    or chunk deletion changes the digest, which changes the FAQ cache key. This is what
    makes "publish a new policy version -> old cache cannot be served" true even before
    the old Redis entry expires.
    """
    payload = [
        {
            "document_id": row.document_id,
            "current_version_id": row.current_version_id,
            "version": row.version,
            "document_status": row.document_status,
            "document_updated_at": _iso(row.document_updated_at),
            "effective_from": _iso(row.effective_from),
            "effective_to": _iso(row.effective_to),
            "parse_status": row.parse_status,
        }
        for row in sorted(rows, key=lambda item: item.document_id)
    ]
    payload.append(
        {
            "chunk_updated_at": _iso(chunk_updated_at),
            "enabled_chunks": enabled_chunks,
        }
    )
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


async def load_knowledge_version_digest(
    session: AsyncSession,
    *,
    shop_id: UUID,
    knowledge_base_id: UUID | None = None,
    at: datetime | None = None,
) -> str:
    """Return the current knowledge-version digest for a shop (and optional KB).

    Only versions effective at ``at`` participate: when a version expires or a new one
    becomes effective, the row set changes and so does the digest.
    """
    moment = at or datetime.now(UTC)
    stmt = (
        sa.select(
            KnowledgeDocument.id,
            KnowledgeDocument.current_version_id,
            KnowledgeDocument.status,
            KnowledgeDocument.updated_at.label("document_updated_at"),
            KnowledgeVersion.version,
            KnowledgeVersion.effective_from,
            KnowledgeVersion.effective_to,
            KnowledgeVersion.parse_status,
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
            KnowledgeDocument.deleted_at.is_(None),
        )
    )
    if knowledge_base_id is not None:
        stmt = stmt.where(KnowledgeDocument.knowledge_base_id == knowledge_base_id)
    raw_rows = (await session.execute(stmt)).all()

    rows: list[KnowledgeVersionRow] = []
    version_ids: list[UUID] = []
    for raw in raw_rows:
        data = raw._mapping
        effective_from = data["effective_from"]
        effective_to = data["effective_to"]
        usable = effective_from is None or (
            effective_from <= moment and (effective_to is None or effective_to > moment)
        )
        if not usable:
            continue
        current_version_id = data["current_version_id"]
        if current_version_id is not None:
            version_ids.append(current_version_id)
        rows.append(
            KnowledgeVersionRow(
                document_id=str(data["id"]),
                current_version_id=str(current_version_id) if current_version_id else None,
                version=data["version"],
                document_status=str(data["status"]),
                document_updated_at=data["document_updated_at"],
                effective_from=effective_from,
                effective_to=effective_to,
                parse_status=str(data["parse_status"]) if data["parse_status"] else None,
            )
        )

    chunk_updated_at: datetime | None = None
    enabled_chunks = 0
    if version_ids:
        chunk_stats = (
            await session.execute(
                sa.select(
                    sa.func.max(KnowledgeChunk.updated_at),
                    sa.func.count()
                    .filter(
                        sa.and_(
                            KnowledgeChunk.is_enabled.is_(True),
                            KnowledgeChunk.deleted_at.is_(None),
                        )
                    )
                    .label("enabled_chunks"),
                ).where(
                    KnowledgeChunk.shop_id == shop_id,
                    KnowledgeChunk.version_id.in_(version_ids),
                )
            )
        ).one()
        chunk_updated_at = chunk_stats[0]
        enabled_chunks = int(chunk_stats[1] or 0)

    return version_digest_from_rows(
        rows, chunk_updated_at=chunk_updated_at, enabled_chunks=enabled_chunks
    )


__all__ = [
    "ChunkMetadata",
    "KnowledgeVersionRow",
    "authorization_issues",
    "load_chunk_metadata",
    "load_knowledge_version_digest",
    "version_digest_from_rows",
]
