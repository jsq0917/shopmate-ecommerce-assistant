"""The admin upload worker re-parses the rows the API created (stage 16).

``POST /admin/documents`` writes document + version + queued job and stores the file; the
worker must then run the **unchanged** stage-5/7 ``ingest_source`` against those ids, not
create a parallel document. This test proves that with the fake embedding provider and
``milvus_enabled=False``, so it needs PostgreSQL but no torch and no Milvus.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.db.models import (
    IngestionJob,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
    Shop,
)
from shopmate_ecommerce_assistant.db.repositories.knowledge_admin import (
    KnowledgeAdminRepository,
    KnowledgeBaseRow,
)
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.rag.ingest.worker import run_ingestion_job
from tests.support.fake_embeddings import FakeHybridEmbeddingProvider

pytestmark = pytest.mark.integration

BODY = """# 阶段16 上传政策

## 退货期限

消费者需在签收后七日内提交退货申请，并提供订单号与实物照片。

## 退款方式

退款原路返回，审核通过后三个工作日内到账。
"""


def _shop_dir(root: Path) -> Path:
    return root / "uploads" / uuid4().hex


async def test_worker_reparses_the_uploaded_version_in_place(
    settings: Settings, session: AsyncSession, tmp_path: Path
) -> None:
    shop = Shop(id=uuid4(), name="阶段16 worker 店铺")
    session.add(shop)
    await session.commit()

    kb = KnowledgeBase(id=uuid4(), shop_id=shop.id, name="阶段16 worker 知识库")
    session.add(kb)
    await session.commit()

    base_dir = tmp_path
    relative = f"uploads/{uuid4().hex}/stage16-worker.md"
    target = base_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(BODY, encoding="utf-8")

    repo = KnowledgeAdminRepository(session)
    uploaded = await repo.create_uploaded_document(
        shop_id=shop.id,
        knowledge_base=KnowledgeBaseRow(
            id=kb.id,
            name=kb.name,
            locale="zh-CN",
            region="CN",
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        document_key="worker-fixture",
        title="阶段16 上传政策",
        doc_type="policy",
        locale="zh-CN",
        region="CN",
        effective_from=datetime.now(UTC) - timedelta(days=1),
        effective_to=None,
        source_uri=relative,
        filename=target.name,
        mime_type="text/markdown",
        content_hash=b"\x00" * 32,
        created_by=None,
    )

    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        outcome = await run_ingestion_job(
            session_factory=factory,
            settings=settings,
            embedder=FakeHybridEmbeddingProvider(),
            store=None,
            version_id=uploaded.version_id,
            milvus_enabled=False,
            base_dir=base_dir,
        )
        assert outcome is not None
        assert outcome.ok, outcome.error_message
        assert outcome.document_id == uploaded.document_id, "must not create a second document"
        assert outcome.version_id == uploaded.version_id
        assert outcome.job_id == uploaded.ingestion_job_id, "the queued job must be reused"
        assert outcome.child_count > 0

        async with factory() as verify:
            status = await verify.scalar(
                sa.select(KnowledgeVersion.parse_status).where(
                    KnowledgeVersion.id == uploaded.version_id
                )
            )
            job_status = await verify.scalar(
                sa.select(IngestionJob.status).where(IngestionJob.id == uploaded.ingestion_job_id)
            )
            jobs = await verify.scalar(
                sa.select(sa.func.count())
                .select_from(IngestionJob)
                .where(IngestionJob.version_id == uploaded.version_id)
            )
            chunks = await verify.scalar(
                sa.select(sa.func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.version_id == uploaded.version_id)
            )
        assert str(status) == "ready"
        assert str(job_status) == "succeeded"
        assert jobs == 1, "one upload maps to exactly one job row"
        assert chunks == outcome.chunk_count
    finally:
        await engine.dispose()
        async with factory() as cleanup:
            await cleanup.execute(
                sa.delete(KnowledgeChunk).where(KnowledgeChunk.shop_id == shop.id)
            )
            await cleanup.execute(
                sa.delete(IngestionJob).where(IngestionJob.shop_id == shop.id)
            )
            await cleanup.execute(
                sa.delete(KnowledgeVersion).where(KnowledgeVersion.shop_id == shop.id)
            )
            await cleanup.execute(
                sa.delete(KnowledgeDocument).where(KnowledgeDocument.shop_id == shop.id)
            )
            await cleanup.execute(sa.delete(KnowledgeBase).where(KnowledgeBase.shop_id == shop.id))
            await cleanup.execute(sa.delete(Shop).where(Shop.id == shop.id))
            await cleanup.commit()
        shutil.rmtree(base_dir / "uploads", ignore_errors=True)
