"""Knowledge ingestion worker glue for the admin upload/reindex endpoints.

The API only ever queues a durable ``ingestion_jobs`` row. This module is the single place
that turns that row back into a real parse: it loads the version/document/knowledge-base
triple, rebuilds the :class:`SourceSpec` the pipeline expects, and calls the unchanged
stage-5/7 :func:`ingest_source` with explicit ids so the existing rows are re-parsed rather
than duplicated.

Keeping it out of the router means it can be exercised with a fake embedding provider and
``milvus_enabled=False`` — no torch, no Milvus required.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from shopmate_ecommerce_assistant.core import paths
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.db.repositories.knowledge_admin import KnowledgeAdminRepository
from shopmate_ecommerce_assistant.rag.embeddings import HybridEmbeddingProvider
from shopmate_ecommerce_assistant.rag.ingest.manifest import SourceSpec
from shopmate_ecommerce_assistant.rag.ingest.pipeline import IngestOutcome, ingest_source
from shopmate_ecommerce_assistant.rag.milvus_store import MilvusKnowledgeStore

logger = logging.getLogger(__name__)


async def run_ingestion_job(
    *,
    session_factory: Callable[[], Any],
    settings: Settings,
    embedder: HybridEmbeddingProvider,
    store: MilvusKnowledgeStore | None,
    version_id: UUID,
    milvus_enabled: bool = True,
    base_dir: Path | None = None,
) -> IngestOutcome | None:
    """Re-parse one queued version; returns ``None`` when the version no longer exists."""
    async with session_factory() as session:
        repo = KnowledgeAdminRepository(session)
        target = await repo.load_ingest_target(version_id=version_id)
        if target is None:
            logger.warning("ingestion target %s disappeared before the worker ran", version_id)
            return None
        spec = SourceSpec(
            document_key=str(target.document_id),
            title=target.title,
            doc_type=target.doc_type,
            version=target.version,
            effective_from=target.effective_from,
            effective_to=target.effective_to,
            locale=target.locale,
            region=target.region,
            knowledge_base=target.knowledge_base_name,
            file=target.source_uri,
        )
        return await ingest_source(
            session=session,
            settings=settings,
            store=store,
            embedder=embedder,
            spec=spec,
            base_dir=base_dir or paths.KNOWLEDGE_DIR,
            shop_id=target.shop_id,
            knowledge_base_id=target.knowledge_base_id,
            document_id=target.document_id,
            version_id=target.version_id,
            job_id=target.job_id,
            milvus_enabled=milvus_enabled,
        )


__all__ = ["run_ingestion_job"]
