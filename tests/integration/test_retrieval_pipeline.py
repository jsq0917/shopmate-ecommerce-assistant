"""End-to-end retrieval: ingest -> Milvus hybrid search -> PostgreSQL re-check -> citation."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.ids import stable_uuid
from shopmate_ecommerce_assistant.db.models import (
    IngestionJob,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
    Shop,
)
from shopmate_ecommerce_assistant.rag.errors import VectorStoreUnavailable
from shopmate_ecommerce_assistant.rag.ingest import SourceSpec, ingest_source
from shopmate_ecommerce_assistant.rag.milvus_store import MilvusKnowledgeStore
from shopmate_ecommerce_assistant.rag.retrieval import (
    DocumentRetriever,
    RetrievalScope,
    session_authorizer,
)
from tests.support.fake_embeddings import FakeHybridEmbeddingProvider

pytestmark = pytest.mark.integration

SHOP_ID = stable_uuid("shop", "demo")
KB_PREFIX = "test-retrieval"
NOW = datetime(2026, 10, 19, tzinfo=UTC)
EMBEDDER = FakeHybridEmbeddingProvider()

SECTIONS = ("退货期限", "退货运费", "不适用商品", "办理流程")


def _body(title: str) -> str:
    paragraph = (
        "消费者自签收之日起七日内可以申请无理由退货，商品需保持完好且配件齐全；"
        "无理由退货的寄回运费由消费者承担，质量问题由商城承担。"
    )
    return f"# {title}\n\n" + "".join(
        f"## {section}\n\n{paragraph * 3}\n\n" for section in SECTIONS
    )


@pytest.fixture(scope="module")
def store(settings: Settings) -> Iterator[MilvusKnowledgeStore]:
    instance = MilvusKnowledgeStore(settings)
    try:
        instance.ensure_collection()
    except VectorStoreUnavailable:
        instance.close()
        pytest.skip("Milvus 不可用：跳过检索集成测试")
    yield instance
    instance.close()


async def _ingest(
    session: AsyncSession,
    store: MilvusKnowledgeStore,
    settings: Settings,
    workspace: Path,
    *,
    key: str,
    kb_name: str,
    version: str,
    effective_from: datetime,
    effective_to: datetime | None,
    extra_title: str,
    shop_id: UUID = SHOP_ID,
) -> UUID:
    (workspace / "policy").mkdir(parents=True, exist_ok=True)
    filename = f"policy/{key}-{version}.md"
    (workspace / filename).write_text(_body(extra_title), encoding="utf-8")
    spec = SourceSpec(
        document_key=key,
        title=extra_title,
        doc_type="policy",
        version=version,
        effective_from=effective_from,
        effective_to=effective_to,
        locale="zh-CN",
        region="CN",
        knowledge_base=kb_name,
        file=filename,
    )
    outcome = await ingest_source(
        session=session,
        settings=settings,
        store=store,
        embedder=EMBEDDER,
        spec=spec,
        base_dir=workspace,
        shop_id=shop_id,
    )
    assert outcome.ok, outcome.error_message
    return outcome.version_id


async def _cleanup(
    session: AsyncSession,
    store: MilvusKnowledgeStore,
    *,
    kb_name: str,
    version_ids: list[UUID],
    shop_id: UUID = SHOP_ID,
) -> None:
    for version_id in version_ids:
        try:
            store.delete_version(str(version_id))
        except VectorStoreUnavailable:  # pragma: no cover
            pass
    if version_ids:
        await session.execute(
            sa.delete(KnowledgeChunk).where(KnowledgeChunk.version_id.in_(version_ids))
        )
        await session.execute(
            sa.delete(IngestionJob).where(IngestionJob.version_id.in_(version_ids))
        )
        await session.execute(
            sa.delete(KnowledgeVersion).where(KnowledgeVersion.id.in_(version_ids))
        )
    kb_id = stable_uuid("knowledge_base", str(shop_id), kb_name)
    document_ids = (
        await session.scalars(
            sa.select(KnowledgeDocument.id).where(KnowledgeDocument.knowledge_base_id == kb_id)
        )
    ).all()
    for document_id in document_ids:
        await session.execute(
            sa.update(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .values(current_version_id=None)
        )
        await session.execute(
            sa.delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        )
    await session.execute(sa.delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    await session.commit()


async def test_hybrid_retrieval_produces_citable_evidence(
    session: AsyncSession, store: MilvusKnowledgeStore, settings: Settings, tmp_path: Path
) -> None:
    kb_name = f"{KB_PREFIX}-{uuid4().hex[:8]}"
    kb_id = str(stable_uuid("knowledge_base", str(SHOP_ID), kb_name))
    version_ids: list[UUID] = []
    try:
        version_ids.append(
            await _ingest(
                session,
                store,
                settings,
                tmp_path,
                key=f"retrieval-{uuid4().hex[:8]}",
                kb_name=kb_name,
                version="2026.10.1",
                effective_from=datetime(2026, 10, 1, tzinfo=UTC),
                effective_to=None,
                extra_title="检索测试退货政策",
            )
        )
        retriever = DocumentRetriever(
            settings=settings,
            provider=EMBEDDER,
            store=store,
            authorizer=session_authorizer(session),
        )
        scope = RetrievalScope(
            shop_id=str(SHOP_ID),
            knowledge_base_id=kb_id,
            locale="zh-CN",
            region="CN",
            at=NOW,
        )

        result = await retriever.retrieve("无理由退货的运费由谁承担？", scope)

        assert result.citations, "应检索到可引用片段"
        first = result.citations[0]
        assert first.title == "检索测试退货政策"
        assert first.version == "2026.10.1"
        assert first.heading
        assert first.citation_id.startswith("cit_")
        assert first.snippet
        assert result.audit["branch"] == {"dense": "ok", "sparse": "ok"}
        assert result.audit["embedding"]["fingerprint"] == "test-fingerprint"
        assert result.audit["dense_limit"] == settings.retrieval_dense_limit
        assert result.audit["sparse_limit"] == settings.retrieval_sparse_limit
        assert result.audit["rrf_k"] == settings.retrieval_rrf_k

        other_shop = await retriever.retrieve(
            "无理由退货的运费由谁承担？",
            RetrievalScope(shop_id=str(uuid4()), knowledge_base_id=kb_id, at=NOW),
        )
        assert other_shop.citations == (), "跨店铺不得返回任何引用"
    finally:
        await _cleanup(session, store, kb_name=kb_name, version_ids=version_ids)


async def test_another_shops_knowledge_is_never_retrieved(
    session: AsyncSession, store: MilvusKnowledgeStore, settings: Settings, tmp_path: Path
) -> None:
    """SEC-04 / §16.2.8：另一店铺的真实知识不得进入本店铺的检索结果。

    Unlike a random-shop scope, this test *ingests* documents that genuinely belong to a
    second shop, so the isolation being verified is the Milvus ``shop_id`` filter plus the
    PostgreSQL re-check — not merely the absence of data.
    """
    other_shop_id = uuid4()
    session.add(Shop(id=other_shop_id, name="跨店隔离测试店铺"))
    await session.commit()

    kb_name_a = f"{KB_PREFIX}-{uuid4().hex[:8]}"
    kb_name_b = f"{KB_PREFIX}-{uuid4().hex[:8]}"
    version_ids: list[UUID] = []
    try:
        version_a = await _ingest(
            session,
            store,
            settings,
            tmp_path,
            key=f"shop-a-{uuid4().hex[:8]}",
            kb_name=kb_name_a,
            version="2026.10.1",
            effective_from=datetime(2026, 10, 1, tzinfo=UTC),
            effective_to=None,
            extra_title="A 店铺退货政策",
        )
        version_ids.append(version_a)
        version_b = await _ingest(
            session,
            store,
            settings,
            tmp_path,
            key=f"shop-b-{uuid4().hex[:8]}",
            kb_name=kb_name_b,
            version="2026.10.1",
            effective_from=datetime(2026, 10, 1, tzinfo=UTC),
            effective_to=None,
            extra_title="B 店铺退货政策",
            shop_id=other_shop_id,
        )
        version_ids.append(version_b)

        retriever = DocumentRetriever(
            settings=settings,
            provider=EMBEDDER,
            store=store,
            authorizer=session_authorizer(session),
        )

        # A query in shop A, with *no* knowledge-base narrowing, must never surface B.
        result_a = await retriever.retrieve(
            "无理由退货的运费由谁承担？",
            RetrievalScope(shop_id=str(SHOP_ID), locale="zh-CN", region="CN", at=NOW),
        )
        assert result_a.citations, "本店铺应有可引用片段"
        # Shop A also owns the seeded demo corpus, so the invariant is "B never appears",
        # not "only this test's version appears".
        assert str(version_a) in {str(c.version_id) for c in result_a.citations}
        assert str(version_b) not in {str(c.version_id) for c in result_a.citations}
        assert "B 店铺退货政策" not in {c.title for c in result_a.citations}

        # The reverse direction holds too: shop B only sees its own document.
        result_b = await retriever.retrieve(
            "无理由退货的运费由谁承担？",
            RetrievalScope(shop_id=str(other_shop_id), locale="zh-CN", region="CN", at=NOW),
        )
        assert result_b.citations
        assert all(str(c.version_id) == str(version_b) for c in result_b.citations)
        assert "A 店铺退货政策" not in {c.title for c in result_b.citations}
    finally:
        await _cleanup(
            session,
            store,
            kb_name=kb_name_a,
            version_ids=[v for v in version_ids if v],
        )
        await _cleanup(
            session,
            store,
            kb_name=kb_name_b,
            version_ids=[version_b] if "version_b" in locals() else [],
            shop_id=other_shop_id,
        )
        await session.execute(sa.delete(Shop).where(Shop.id == other_shop_id))
        await session.commit()


async def test_expired_version_never_becomes_evidence(
    session: AsyncSession, store: MilvusKnowledgeStore, settings: Settings, tmp_path: Path
) -> None:
    kb_name = f"{KB_PREFIX}-{uuid4().hex[:8]}"
    kb_id = str(stable_uuid("knowledge_base", str(SHOP_ID), kb_name))
    version_ids: list[UUID] = []
    key = f"retrieval-{uuid4().hex[:8]}"
    try:
        version_ids.append(
            await _ingest(
                session,
                store,
                settings,
                tmp_path,
                key=key,
                kb_name=kb_name,
                version="2026.07.1",
                effective_from=datetime(2026, 7, 1, tzinfo=UTC),
                effective_to=datetime(2026, 10, 1, tzinfo=UTC),
                extra_title="已过期退货政策",
            )
        )
        retriever = DocumentRetriever(
            settings=settings,
            provider=EMBEDDER,
            store=store,
            authorizer=session_authorizer(session),
        )
        scope = RetrievalScope(
            shop_id=str(SHOP_ID),
            knowledge_base_id=kb_id,
            locale="zh-CN",
            region="CN",
            at=NOW,
        )

        result = await retriever.retrieve("无理由退货的运费由谁承担？", scope)

        assert result.citations == ()
        assert result.evidence_sufficient is False
        assert result.audit["rejected"].get("expired", 0) >= 0
    finally:
        await _cleanup(session, store, kb_name=kb_name, version_ids=version_ids)
