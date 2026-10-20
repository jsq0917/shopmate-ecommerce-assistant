"""End-to-end ingestion tests: PostgreSQL metadata, Milvus vectors and filters."""

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
    ParseStatus,
)
from shopmate_ecommerce_assistant.rag.errors import VectorStoreUnavailable
from shopmate_ecommerce_assistant.rag.ingest import SourceSpec, ingest_source
from shopmate_ecommerce_assistant.rag.milvus_store import MilvusKnowledgeStore
from tests.support.fake_embeddings import FakeHybridEmbeddingProvider

pytestmark = pytest.mark.integration

SHOP_ID = stable_uuid("shop", "demo")
EMBEDDER = FakeHybridEmbeddingProvider()
KB_PREFIX = "test-fixtures"
NOW = datetime(2026, 10, 19, tzinfo=UTC)
SECTIONS = ("生效范围", "退货期限", "申请材料", "审核流程", "退款方式", "争议处理")

PARAGRAPH = (
    "本条规定了退货办理的时间窗口、举证要求与审核流程，"
    "消费者需在签收后七日内提交申请，并提供订单号与实物照片。"
)


def _document_body(title: str, *, extra: str = "", repeat: int = 8) -> str:
    """Build a policy document large enough to need several parents and children."""
    return f"# {title}\n\n" + "".join(
        f"## {section}\n\n{PARAGRAPH * repeat}{extra}\n\n" for section in SECTIONS
    )


def _kb_name() -> str:
    return f"{KB_PREFIX}-{uuid4().hex[:8]}"


def _kb_id(kb_name: str) -> str:
    return str(stable_uuid("knowledge_base", str(SHOP_ID), kb_name))


def _search(
    store: MilvusKnowledgeStore,
    query: str,
    *,
    kb_id: str,
    at: datetime,
    region: str = "CN",
    limit: int = 5,
):
    """Dense search helper used only for wiring assertions in these tests."""
    expr = store.build_filter(shop_id=str(SHOP_ID), knowledge_base_id=kb_id, region=region, at=at)
    return store.dense_search(EMBEDDER.embed_query(query), expr=expr, limit=limit)


def _spec(
    *,
    key: str,
    version: str,
    effective_from: str,
    effective_to: str | None,
    knowledge_base: str,
    region: str = "CN",
    file: str | None = None,
) -> SourceSpec:
    return SourceSpec(
        document_key=key,
        title=f"测试退货政策 {key}",
        doc_type="policy",
        version=version,
        effective_from=datetime.fromisoformat(effective_from.replace("Z", "+00:00")),
        effective_to=datetime.fromisoformat(effective_to.replace("Z", "+00:00"))
        if effective_to
        else None,
        locale="zh-CN",
        region=region,
        knowledge_base=knowledge_base,
        file=file or f"policy/{key}-{version}.md",
    )


@pytest.fixture(scope="module")
def store(settings: Settings) -> Iterator[MilvusKnowledgeStore | None]:
    instance = MilvusKnowledgeStore(settings)
    try:
        instance.ensure_collection()
    except VectorStoreUnavailable:
        instance.close()
        pytest.skip("Milvus 不可用：跳过 ingestion 集成测试")
    yield instance
    instance.close()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "policy").mkdir(parents=True, exist_ok=True)
    return tmp_path


async def _cleanup(
    session: AsyncSession,
    store: MilvusKnowledgeStore | None,
    *,
    version_ids: list[UUID],
    document_ids: list[UUID],
) -> None:
    for version_id in version_ids:
        if store is not None:
            try:
                store.delete_version(str(version_id))
            except VectorStoreUnavailable:  # pragma: no cover - best effort
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
    for document_id in document_ids:
        await session.execute(
            sa.update(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .values(current_version_id=None)
        )
        await session.execute(
            sa.delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        )
    await session.execute(sa.delete(KnowledgeBase).where(KnowledgeBase.name.like(f"{KB_PREFIX}%")))
    await session.commit()


async def test_ingest_builds_parent_child_metadata_and_vectors(
    session, store: MilvusKnowledgeStore, settings: Settings, workspace: Path
) -> None:
    key = f"test-return-{uuid4().hex[:8]}"
    kb_name = _kb_name()
    body_title = "测试退货政策"
    (workspace / "policy" / f"{key}-2026.10.1.md").write_text(
        _document_body(body_title), encoding="utf-8"
    )
    spec = _spec(
        key=key,
        version="2026.10.1",
        effective_from="2026-10-01T00:00:00Z",
        effective_to=None,
        knowledge_base=kb_name,
    )
    version_ids: list[UUID] = []
    document_ids: list[UUID] = []

    try:
        outcome = await ingest_source(
            session=session,
            settings=settings,
            store=store,
            embedder=EMBEDDER,
            spec=spec,
            base_dir=workspace,
            shop_id=SHOP_ID,
        )
        version_ids.append(outcome.version_id)
        document_ids.append(outcome.document_id)

        assert outcome.ok, outcome.error_message
        assert outcome.parent_count >= 1
        assert outcome.child_count >= 2
        assert outcome.milvus_count == outcome.child_count

        version = await session.get(KnowledgeVersion, outcome.version_id)
        assert version is not None
        assert version.parse_status == ParseStatus.READY.value
        assert version.content_hash != b""
        assert version.effective_to is None

        document = await session.get(KnowledgeDocument, outcome.document_id)
        assert document is not None
        assert document.current_version_id == outcome.version_id

        chunks = (
            await session.scalars(
                sa.select(KnowledgeChunk)
                .where(KnowledgeChunk.version_id == outcome.version_id)
                .order_by(KnowledgeChunk.chunk_index)
            )
        ).all()
        parents = [chunk for chunk in chunks if chunk.parent_id is None]
        children = [chunk for chunk in chunks if chunk.parent_id is not None]
        assert len(parents) == outcome.parent_count
        assert len(children) == outcome.child_count

        parent_ids = {parent.id for parent in parents}
        parent_text = {parent.id: parent.text for parent in parents}
        for child in children:
            assert child.is_enabled is True
            assert child.parent_id in parent_ids
            assert child.heading_path, "子块必须保留标题路径"
            assert child.heading_path[0] == body_title, "标题路径应保留文档 H1"
            assert child.text in parent_text[child.parent_id]
            assert child.token_count > 0
            assert child.content_hash != b""
            embedding = child.metadata_jsonb["embedding"]
            assert embedding["embedded"] is True
            assert embedding["dimension"] == 1024
            assert embedding["fingerprint"] == "test-fingerprint"
            assert embedding["model"] == "fake-hybrid"
        assert all(parent.is_enabled is False for parent in parents)
        assert all(parent.metadata_jsonb["embedding"]["embedded"] is False for parent in parents)

        job = await session.scalar(
            sa.select(IngestionJob).where(IngestionJob.version_id == outcome.version_id)
        )
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempt_count == 1

        assert store.count_version(str(outcome.version_id)) == outcome.child_count

        hits = _search(store, "退货申请需要提供哪些材料", kb_id=_kb_id(kb_name), at=NOW)
        assert any(hit.version_id == str(outcome.version_id) for hit in hits)
    finally:
        await _cleanup(session, store, version_ids=version_ids, document_ids=document_ids)


async def test_reingest_keeps_chunk_count_stable(
    session, store: MilvusKnowledgeStore, settings: Settings, workspace: Path
) -> None:
    key = f"test-idempotent-{uuid4().hex[:8]}"
    kb_name = _kb_name()
    (workspace / "policy" / f"{key}-2026.10.1.md").write_text(
        _document_body("幂等入库测试"), encoding="utf-8"
    )
    spec = _spec(
        key=key,
        version="2026.10.1",
        effective_from="2026-10-01T00:00:00Z",
        effective_to=None,
        knowledge_base=kb_name,
    )
    version_ids: list[UUID] = []
    document_ids: list[UUID] = []

    try:
        first = await ingest_source(
            session=session,
            settings=settings,
            store=store,
            embedder=EMBEDDER,
            spec=spec,
            base_dir=workspace,
            shop_id=SHOP_ID,
        )
        version_ids.append(first.version_id)
        document_ids.append(first.document_id)
        first_chunk_ids = set(
            (
                await session.scalars(
                    sa.select(KnowledgeChunk.id).where(
                        KnowledgeChunk.version_id == first.version_id
                    )
                )
            ).all()
        )

        second = await ingest_source(
            session=session,
            settings=settings,
            store=store,
            embedder=EMBEDDER,
            spec=spec,
            base_dir=workspace,
            shop_id=SHOP_ID,
        )

        assert second.ok
        assert second.chunk_count == first.chunk_count
        second_chunk_ids = set(
            (
                await session.scalars(
                    sa.select(KnowledgeChunk.id).where(
                        KnowledgeChunk.version_id == second.version_id
                    )
                )
            ).all()
        )
        assert second_chunk_ids == first_chunk_ids, "重复入库不应产生新片段 ID"
        assert store.count_version(str(first.version_id)) == first.child_count

        jobs = (
            await session.scalars(
                sa.select(IngestionJob)
                .where(IngestionJob.version_id == first.version_id)
                .order_by(IngestionJob.attempt_count)
            )
        ).all()
        assert [job.attempt_count for job in jobs] == [1, 2]
        assert all(job.status == "succeeded" for job in jobs)
    finally:
        await _cleanup(session, store, version_ids=version_ids, document_ids=document_ids)


async def test_expired_version_is_not_retrievable(
    session, store: MilvusKnowledgeStore, settings: Settings, workspace: Path
) -> None:
    key = f"test-version-{uuid4().hex[:8]}"
    kb_name = _kb_name()
    (workspace / "policy" / f"{key}-2026.07.1.md").write_text(
        _document_body("版本过滤测试", extra="旧版本内容。"), encoding="utf-8"
    )
    (workspace / "policy" / f"{key}-2026.10.1.md").write_text(
        _document_body("版本过滤测试", extra="新版本内容。"), encoding="utf-8"
    )
    old_spec = _spec(
        key=key,
        version="2026.07.1",
        effective_from="2026-07-01T00:00:00Z",
        effective_to="2026-10-01T00:00:00Z",
        knowledge_base=kb_name,
    )
    new_spec = _spec(
        key=key,
        version="2026.10.1",
        effective_from="2026-10-01T00:00:00Z",
        effective_to=None,
        knowledge_base=kb_name,
    )
    version_ids: list[UUID] = []
    document_ids: list[UUID] = []

    try:
        old = await ingest_source(
            session=session,
            settings=settings,
            store=store,
            embedder=EMBEDDER,
            spec=old_spec,
            base_dir=workspace,
            shop_id=SHOP_ID,
        )
        new = await ingest_source(
            session=session,
            settings=settings,
            store=store,
            embedder=EMBEDDER,
            spec=new_spec,
            base_dir=workspace,
            shop_id=SHOP_ID,
        )
        version_ids.extend([old.version_id, new.version_id])
        document_ids.extend([old.document_id, new.document_id])
        assert old.ok and new.ok

        kb_id = _kb_id(kb_name)
        current_hits = _search(store, "退货期限是多久", kb_id=kb_id, at=NOW, limit=10)
        old_hits = _search(
            store, "退货期限是多久", kb_id=kb_id, at=datetime(2026, 8, 1, tzinfo=UTC), limit=10
        )

        current_versions = {hit.version_id for hit in current_hits}
        previous_versions = {hit.version_id for hit in old_hits}
        assert str(new.version_id) in current_versions
        assert str(old.version_id) not in current_versions, "过期版本不得进入当前检索结果"
        assert str(old.version_id) in previous_versions
        assert str(new.version_id) not in previous_versions
    finally:
        await _cleanup(session, store, version_ids=version_ids, document_ids=document_ids)


async def test_region_filter_isolates_cross_border_policy(
    session, store: MilvusKnowledgeStore, settings: Settings, workspace: Path
) -> None:
    key = f"test-region-{uuid4().hex[:8]}"
    kb_name = _kb_name()
    (workspace / "policy" / f"{key}-cn.md").write_text(
        _document_body("地区测试政策", extra="中国大陆地区适用。"), encoding="utf-8"
    )
    (workspace / "policy" / f"{key}-sg.md").write_text(
        _document_body("地区测试政策", extra="新加坡地区适用。"), encoding="utf-8"
    )
    cn_spec = _spec(
        key=key,
        version="cn",
        effective_from="2026-09-01T00:00:00Z",
        effective_to=None,
        knowledge_base=kb_name,
        region="CN",
        file=f"policy/{key}-cn.md",
    )
    sg_spec = _spec(
        key=key,
        version="sg",
        effective_from="2026-09-01T00:00:00Z",
        effective_to=None,
        knowledge_base=kb_name,
        region="SG",
        file=f"policy/{key}-sg.md",
    )
    version_ids: list[UUID] = []
    document_ids: list[UUID] = []

    try:
        cn = await ingest_source(
            session=session,
            settings=settings,
            store=store,
            embedder=EMBEDDER,
            spec=cn_spec,
            base_dir=workspace,
            shop_id=SHOP_ID,
        )
        sg = await ingest_source(
            session=session,
            settings=settings,
            store=store,
            embedder=EMBEDDER,
            spec=sg_spec,
            base_dir=workspace,
            shop_id=SHOP_ID,
        )
        version_ids.extend([cn.version_id, sg.version_id])
        document_ids.extend([cn.document_id, sg.document_id])
        assert cn.ok and sg.ok

        kb_id = _kb_id(kb_name)
        cn_hits = _search(store, "退货期限", kb_id=kb_id, at=NOW, region="CN", limit=10)
        sg_hits = _search(store, "退货期限", kb_id=kb_id, at=NOW, region="SG", limit=10)

        cn_versions = {hit.version_id for hit in cn_hits}
        sg_versions = {hit.version_id for hit in sg_hits}
        assert cn_versions == {str(cn.version_id)}, "CN 检索不得命中 SG 政策"
        assert sg_versions == {str(sg.version_id)}, "SG 检索不得命中 CN 政策"
        assert all(hit.metadata["region"] == "CN" for hit in cn_hits)
        assert all(hit.metadata["region"] == "SG" for hit in sg_hits)
    finally:
        await _cleanup(session, store, version_ids=version_ids, document_ids=document_ids)


async def test_missing_document_is_marked_failed_with_reason(
    session, store: MilvusKnowledgeStore, settings: Settings, workspace: Path
) -> None:
    key = f"test-missing-{uuid4().hex[:8]}"
    kb_name = _kb_name()
    spec = _spec(
        key=key,
        version="2026.10.1",
        effective_from="2026-10-01T00:00:00Z",
        effective_to=None,
        knowledge_base=kb_name,
        file=f"policy/{key}-missing.md",
    )
    version_ids: list[UUID] = []
    document_ids: list[UUID] = []

    try:
        outcome = await ingest_source(
            session=session,
            settings=settings,
            store=store,
            embedder=EMBEDDER,
            spec=spec,
            base_dir=workspace,
            shop_id=SHOP_ID,
        )
        version_ids.append(outcome.version_id)
        document_ids.append(outcome.document_id)

        assert outcome.status == ParseStatus.FAILED.value
        assert outcome.error_code == "FILE_NOT_FOUND"
        assert outcome.chunk_count == 0
        assert outcome.milvus_count == 0

        version = await session.get(KnowledgeVersion, outcome.version_id)
        assert version is not None
        assert version.parse_status == ParseStatus.FAILED.value
        assert version.failure_code == "FILE_NOT_FOUND"
        assert version.failure_message_safe

        job = await session.scalar(
            sa.select(IngestionJob).where(IngestionJob.version_id == outcome.version_id)
        )
        assert job is not None
        assert job.status == "failed"
        assert job.error_code == "FILE_NOT_FOUND"

        chunks = await session.scalar(
            sa.select(sa.func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.version_id == outcome.version_id)
        )
        assert chunks == 0, "失败文档不得留下可见片段"
        assert store.count_version(str(outcome.version_id)) == 0
    finally:
        await _cleanup(session, store, version_ids=version_ids, document_ids=document_ids)


async def test_corrupt_document_is_marked_failed_with_parse_error(
    session, store: MilvusKnowledgeStore, settings: Settings, workspace: Path
) -> None:
    key = f"test-corrupt-{uuid4().hex[:8]}"
    kb_name = _kb_name()
    corrupt = workspace / "policy" / f"{key}-broken.pdf"
    corrupt.write_bytes(b"%PDF-1.4 not really a pdf")
    spec = _spec(
        key=key,
        version="2026.10.1",
        effective_from="2026-10-01T00:00:00Z",
        effective_to=None,
        knowledge_base=kb_name,
        file=f"policy/{key}-broken.pdf",
    )
    version_ids: list[UUID] = []
    document_ids: list[UUID] = []

    try:
        outcome = await ingest_source(
            session=session,
            settings=settings,
            store=store,
            embedder=EMBEDDER,
            spec=spec,
            base_dir=workspace,
            shop_id=SHOP_ID,
        )
        version_ids.append(outcome.version_id)
        document_ids.append(outcome.document_id)

        assert outcome.status == ParseStatus.FAILED.value
        assert outcome.error_code == "PARSE_FAILED"
        version = await session.get(KnowledgeVersion, outcome.version_id)
        assert version is not None
        assert version.parse_status == ParseStatus.FAILED.value
        assert version.failure_code == "PARSE_FAILED"
    finally:
        await _cleanup(session, store, version_ids=version_ids, document_ids=document_ids)


async def test_path_outside_workspace_is_rejected(
    session, store: MilvusKnowledgeStore, settings: Settings, workspace: Path
) -> None:
    key = f"test-escape-{uuid4().hex[:8]}"
    kb_name = _kb_name()
    spec = _spec(
        key=key,
        version="2026.10.1",
        effective_from="2026-10-01T00:00:00Z",
        effective_to=None,
        knowledge_base=kb_name,
        file="../../outside.md",
    )
    version_ids: list[UUID] = []
    document_ids: list[UUID] = []

    try:
        outcome = await ingest_source(
            session=session,
            settings=settings,
            store=store,
            embedder=EMBEDDER,
            spec=spec,
            base_dir=workspace,
            shop_id=SHOP_ID,
        )
        version_ids.append(outcome.version_id)
        document_ids.append(outcome.document_id)

        assert outcome.status == ParseStatus.FAILED.value
        assert outcome.error_code == "UNSAFE_SOURCE_PATH"
        assert store.count_version(str(outcome.version_id)) == 0
    finally:
        await _cleanup(session, store, version_ids=version_ids, document_ids=document_ids)
