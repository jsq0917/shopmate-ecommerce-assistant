"""Reader for the knowledge bases a chat user may select (stage 18).

The course brief requires the chat page to offer knowledge bases as a multi-select. This
module owns the *user-facing* read path, which is deliberately narrower than the admin one
(``knowledge_admin``): only the caller's shop, and only ``status=active`` knowledge bases.

Visibility rule (documented in ``docs/06-api.md``): a knowledge base is selectable when it
belongs to the current shop and is active. There is no per-user ACL in this project, so
"visible to the user" is exactly "visible to the shop".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.db.models import (
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeVersion,
)


@dataclass(frozen=True, slots=True)
class KnowledgeBaseOption:
    """One selectable knowledge base."""

    id: UUID
    name: str
    locale: str
    region: str


@dataclass(frozen=True, slots=True)
class DocumentAsset:
    """The stored original file behind a document's current version."""

    document_id: UUID
    title: str
    source_uri: str
    filename: str
    mime_type: str


class KnowledgeScopeRepository:
    """Shop-scoped reads used by the conversation knowledge-base selection."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self, *, shop_id: UUID) -> tuple[KnowledgeBaseOption, ...]:
        """Return every active knowledge base of the shop, ordered by creation."""
        stmt = (
            sa.select(KnowledgeBase)
            .where(
                KnowledgeBase.shop_id == shop_id,
                KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE,
            )
            .order_by(KnowledgeBase.created_at, KnowledgeBase.id)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return tuple(
            KnowledgeBaseOption(id=row.id, name=row.name, locale=row.locale, region=row.region)
            for row in rows
        )

    async def selectable_ids(
        self, *, shop_id: UUID, candidate_ids: Sequence[UUID]
    ) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]:
        """Split ``candidate_ids`` into (selectable, rejected) preserving input order.

        A rejected id is either from another shop (including a nonexistent one — the two
        are indistinguishable on purpose) or inactive. Callers must not persist a partial
        selection, so the rejection list is returned rather than silently filtered.
        """
        wanted: list[UUID] = []
        for item in candidate_ids:
            if item not in wanted:
                wanted.append(item)
        if not wanted:
            return (), ()
        stmt = sa.select(KnowledgeBase.id).where(
            KnowledgeBase.shop_id == shop_id,
            KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE,
            KnowledgeBase.id.in_(wanted),
        )
        allowed = set((await self._session.execute(stmt)).scalars().all())
        selectable = tuple(item for item in wanted if item in allowed)
        rejected = tuple(item for item in wanted if item not in allowed)
        return selectable, rejected

    async def document_asset(self, *, shop_id: UUID, document_id: UUID) -> DocumentAsset | None:
        """Return the current version's stored file for an in-scope image document.

        Only images are served: the endpoint exists so a citation can point back at the
        screenshot its text was OCR'd from. A document from another shop, a deleted one or
        one without a current version is indistinguishable from a missing one (``None``),
        so the caller can answer 404 without leaking existence.
        """
        stmt = (
            sa.select(KnowledgeDocument, KnowledgeVersion)
            .join(
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
                KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE,
            )
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        document, version = row
        return DocumentAsset(
            document_id=document.id,
            title=document.title,
            source_uri=version.source_uri,
            filename=version.source_filename,
            mime_type=version.mime_type,
        )


__all__ = ["DocumentAsset", "KnowledgeBaseOption", "KnowledgeScopeRepository"]
