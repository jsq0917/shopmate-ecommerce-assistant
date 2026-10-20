"""Milvus schema, dual-vector write and hybrid-search tests against the local instance."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pymilvus import MilvusClient

from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.rag.errors import (
    InvalidEmbeddingError,
    VectorStoreUnavailable,
)
from shopmate_ecommerce_assistant.rag.milvus_store import (
    DENSE_FIELD,
    SPARSE_FIELD,
    ChunkVector,
    MilvusKnowledgeStore,
    collect_vector_stats,
)
from tests.support.fake_embeddings import FakeHybridEmbeddingProvider

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def store() -> Iterator[MilvusKnowledgeStore]:
    instance = MilvusKnowledgeStore(get_settings())
    try:
        instance.ensure_collection()
    except VectorStoreUnavailable:
        instance.close()
        pytest.skip("Milvus 不可用：跳过向量库集成测试")
    yield instance
    instance.close()


@pytest.fixture
def tenant(store: MilvusKnowledgeStore) -> AsyncIterator[tuple[str, list[str]]]:
    """Yield an isolated shop id plus a mutable list of versions to clean up."""
    shop_id = f"test-shop-{uuid4()}"
    version_ids: list[str] = []
    yield shop_id, version_ids
    for version_id in version_ids:
        try:
            store.delete_version(version_id)
        except VectorStoreUnavailable:  # pragma: no cover - cleanup is best effort
            pass


EMBEDDER = FakeHybridEmbeddingProvider()


def _chunk(
    *,
    chunk_id: str,
    shop_id: str,
    version_id: str,
    region: str,
    effective_from: datetime,
    effective_to: datetime | None,
    text: str,
    doc_type: str = "policy",
    page_no: int | None = 1,
) -> ChunkVector:
    vector = EMBEDDER.embed_query_hybrid(text)
    return ChunkVector(
        chunk_id=chunk_id,
        shop_id=shop_id,
        knowledge_base_id="kb-test",
        document_id="doc-test",
        version_id=version_id,
        doc_type=doc_type,
        locale="zh-CN",
        region=region,
        status="ready",
        effective_from=effective_from,
        effective_to=effective_to,
        page_no=page_no,
        heading_path=("测试政策", "条款"),
        text=text,
        metadata_json='{"is_synthetic": true}',
        dense=vector.dense,
        sparse=vector.sparse,
        embedding_model="fake-hybrid",
    )


def _search(
    store: MilvusKnowledgeStore,
    query: str,
    *,
    shop_id: str,
    at: datetime,
    region: str | None = "CN",
    knowledge_base_id: str | None = None,
    doc_types: list[str] | None = None,
    limit: int = 5,
):
    expr = store.build_filter(
        shop_id=shop_id,
        knowledge_base_id=knowledge_base_id,
        region=region,
        at=at,
        doc_types=doc_types,
    )
    return store.dense_search(EMBEDDER.embed_query(query), expr=expr, limit=limit)


def _hybrid(
    store: MilvusKnowledgeStore,
    query: str,
    *,
    shop_id: str,
    at: datetime,
    region: str | None = "CN",
    limit: int = 5,
):
    vector = EMBEDDER.embed_query_hybrid(query)
    expr = store.build_filter(shop_id=shop_id, region=region, at=at)
    return store.hybrid_search(
        vector.dense,
        vector.sparse,
        expr=expr,
        dense_limit=30,
        sparse_limit=30,
        rrf_k=60,
        limit=limit,
    )


def test_collection_has_both_vector_fields_and_indexes(store: MilvusKnowledgeStore) -> None:
    described = store.assert_compatible()
    assert described["dense_dimension"] == 1024
    assert described["has_sparse"] is True
    assert {DENSE_FIELD, SPARSE_FIELD} <= set(described["indexes"])
    client = MilvusClient(uri=store.uri)
    try:
        detail = client.describe_collection(store.collection)
    finally:
        client.close()
    field_names = {field["name"] for field in detail["fields"]}
    assert {"sparse_vector", "embedding_model", "effective_from", "effective_to"} <= field_names


def test_write_and_hybrid_search(store: MilvusKnowledgeStore, tenant) -> None:
    shop_id, version_ids = tenant
    version_id = str(uuid4())
    version_ids.append(version_id)
    now = datetime(2026, 10, 19, tzinfo=UTC)

    chunks = [
        _chunk(
            chunk_id=str(uuid4()),
            shop_id=shop_id,
            version_id=version_id,
            region="CN",
            effective_from=datetime(2026, 10, 1, tzinfo=UTC),
            effective_to=None,
            text="七天无理由退货自签收之日起计算。",
        ),
        _chunk(
            chunk_id=str(uuid4()),
            shop_id=shop_id,
            version_id=version_id,
            region="CN",
            effective_from=datetime(2026, 10, 1, tzinfo=UTC),
            effective_to=None,
            text="发票抬头需填写完整企业名称与纳税人识别号。",
        ),
    ]

    assert store.upsert_chunks(chunks) == 2
    assert store.count_version(version_id) == 2

    result = _hybrid(store, "无理由退货怎么计算时间", shop_id=shop_id, at=now)
    assert result.hits, "混合检索应返回候选"
    assert result.rrf_k == 60
    assert result.hits[0].text.startswith("七天无理由")
    assert result.hits[0].page_no == 1
    assert result.hits[0].heading_path == ("测试政策", "条款")
    assert result.hits[0].embedding_model == "fake-hybrid"
    assert not _hybrid(store, "无理由退货", shop_id="other-shop", at=now).hits

    store.delete_version(version_id)
    assert store.count_version(version_id) == 0


def test_sparse_vector_is_required_on_write(store: MilvusKnowledgeStore, tenant) -> None:
    shop_id, _ = tenant
    chunk = _chunk(
        chunk_id=str(uuid4()),
        shop_id=shop_id,
        version_id=str(uuid4()),
        region="CN",
        effective_from=datetime(2026, 9, 1, tzinfo=UTC),
        effective_to=None,
        text="sparse 必须存在",
    )
    broken = replace(chunk, sparse={})

    with pytest.raises(InvalidEmbeddingError) as excinfo:
        store.upsert_chunks([broken])
    assert excinfo.value.code == "EMBEDDING_EMPTY_SPARSE"


def test_effective_window_filters_expired_versions(store: MilvusKnowledgeStore, tenant) -> None:
    shop_id, version_ids = tenant
    current_version = str(uuid4())
    expired_version = str(uuid4())
    version_ids.extend([current_version, expired_version])

    query = "退货期限是几天"
    store.upsert_chunks(
        [
            _chunk(
                chunk_id=str(uuid4()),
                shop_id=shop_id,
                version_id=expired_version,
                region="CN",
                effective_from=datetime(2026, 7, 1, tzinfo=UTC),
                effective_to=datetime(2026, 10, 1, tzinfo=UTC),
                text="旧版本：退货期限为七天。",
            ),
            _chunk(
                chunk_id=str(uuid4()),
                shop_id=shop_id,
                version_id=current_version,
                region="CN",
                effective_from=datetime(2026, 10, 1, tzinfo=UTC),
                effective_to=None,
                text="新版本：退货期限为十五天。",
            ),
        ]
    )

    now_hits = _hybrid(store, query, shop_id=shop_id, at=datetime(2026, 10, 19, tzinfo=UTC)).hits
    past_hits = _hybrid(store, query, shop_id=shop_id, at=datetime(2026, 8, 1, tzinfo=UTC)).hits

    assert {hit.version_id for hit in now_hits} == {current_version}
    assert {hit.version_id for hit in past_hits} == {expired_version}


def test_region_and_doc_type_filters_are_applied(store: MilvusKnowledgeStore, tenant) -> None:
    shop_id, version_ids = tenant
    cn_version = str(uuid4())
    sg_version = str(uuid4())
    version_ids.extend([cn_version, sg_version])
    now = datetime(2026, 10, 19, tzinfo=UTC)

    store.upsert_chunks(
        [
            _chunk(
                chunk_id=str(uuid4()),
                shop_id=shop_id,
                version_id=cn_version,
                region="CN",
                effective_from=datetime(2026, 9, 1, tzinfo=UTC),
                effective_to=None,
                text="中国大陆地区退货期限为七天。",
            ),
            _chunk(
                chunk_id=str(uuid4()),
                shop_id=shop_id,
                version_id=sg_version,
                region="SG",
                effective_from=datetime(2026, 9, 1, tzinfo=UTC),
                effective_to=None,
                text="新加坡退货期限为十五天。",
            ),
        ]
    )

    cn_hits = _hybrid(store, "退货期限", shop_id=shop_id, at=now, region="CN").hits
    sg_hits = _hybrid(store, "退货期限", shop_id=shop_id, at=now, region="SG").hits
    warranty_hits = _search(store, "退货期限", shop_id=shop_id, at=now, doc_types=["warranty"])

    assert {hit.version_id for hit in cn_hits} == {cn_version}
    assert {hit.version_id for hit in sg_hits} == {sg_version}
    assert warranty_hits == []


def test_upsert_with_same_chunk_id_is_idempotent(store: MilvusKnowledgeStore, tenant) -> None:
    shop_id, version_ids = tenant
    version_id = str(uuid4())
    version_ids.append(version_id)
    chunk = _chunk(
        chunk_id=str(uuid4()),
        shop_id=shop_id,
        version_id=version_id,
        region="CN",
        effective_from=datetime(2026, 9, 1, tzinfo=UTC),
        effective_to=None,
        text="可重复写入的片段。",
    )

    store.upsert_chunks([chunk])
    store.upsert_chunks([chunk])

    assert store.count_version(version_id) == 1


def test_dimension_mismatch_is_rejected(store: MilvusKnowledgeStore, tenant) -> None:
    shop_id, _ = tenant
    chunk = _chunk(
        chunk_id=str(uuid4()),
        shop_id=shop_id,
        version_id=str(uuid4()),
        region="CN",
        effective_from=datetime(2026, 9, 1, tzinfo=UTC),
        effective_to=None,
        text="维度错误",
    )
    broken = replace(chunk, dense=(0.1, 0.2, 0.3))

    with pytest.raises(InvalidEmbeddingError):
        store.upsert_chunks([broken])


def test_non_normalised_dense_vector_is_rejected_before_any_write(
    store: MilvusKnowledgeStore, tenant
) -> None:
    """Write-side norm assertion: a 0.5-norm vector must not reach the collection.

    Normalisation belongs to the provider; the store's job is to refuse a batch that would
    make COSINE scores incomparable with the query side. Nothing may be written.
    """
    shop_id, _ = tenant
    version_id = str(uuid4())
    chunk = _chunk(
        chunk_id=str(uuid4()),
        shop_id=shop_id,
        version_id=version_id,
        region="CN",
        effective_from=datetime(2026, 9, 1, tzinfo=UTC),
        effective_to=None,
        text="未归一化的向量不应入库。",
    )
    broken = replace(chunk, dense=tuple(value * 0.5 for value in chunk.dense))

    with pytest.raises(InvalidEmbeddingError) as excinfo:
        store.upsert_chunks([broken])
    assert excinfo.value.code == "EMBEDDING_NORM_INVALID"
    assert store.count_version(version_id) == 0


def test_collect_vector_stats_reports_full_sparse_coverage(
    store: MilvusKnowledgeStore, tenant
) -> None:
    shop_id, version_ids = tenant
    version_id = str(uuid4())
    version_ids.append(version_id)
    store.upsert_chunks(
        [
            _chunk(
                chunk_id=str(uuid4()),
                shop_id=shop_id,
                version_id=version_id,
                region="CN",
                effective_from=datetime(2026, 9, 1, tzinfo=UTC),
                effective_to=None,
                text="统计稀疏覆盖率用片段。",
            )
        ]
    )
    stats = collect_vector_stats(store, expr=f'version_id == "{version_id}"')
    assert stats["rows"] == 1
    assert stats["sparse_coverage"] == 1.0
    assert stats["dense_dimensions"] == [1024]
    assert stats["norms_outside_tolerance"] == 0
