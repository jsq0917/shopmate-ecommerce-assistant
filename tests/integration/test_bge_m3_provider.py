"""Real BGE-M3 provider checks (opt-in: needs local weights).

Run with::

    $env:SHOPMATE_RUN_MODEL_TESTS = "1"
    uv run pytest tests/integration/test_bge_m3_provider.py -q

The test is skipped by default so CI and unit runs never download or load ~2.3GB weights.
"""

from __future__ import annotations

import math
import os

import pytest

from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.rag.embeddings import DENSE_DIMENSION, get_bge_m3_provider

pytestmark = pytest.mark.model


def _skip_reason() -> str | None:
    if os.environ.get("SHOPMATE_RUN_MODEL_TESTS") != "1":
        return "未设置 SHOPMATE_RUN_MODEL_TESTS=1：跳过真实模型测试"
    settings = get_settings()
    if not settings.embedding_model_path:
        return "未配置 EMBEDDING_MODEL_PATH：跳过真实模型测试"
    return None


def test_bge_m3_emits_normalised_dense_and_sparse() -> None:
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    provider = get_bge_m3_provider(get_settings())
    metadata = provider.warmup()
    assert metadata.dimension == DENSE_DIMENSION

    batch = provider.embed_documents_hybrid(
        ["消费者自签收之日起七日内可以申请无理由退货。", "发票抬头需填写企业名称与纳税人识别号。"]
    )
    assert len(batch) == 2
    for vector in batch:
        assert len(vector.dense) == DENSE_DIMENSION
        norm = math.sqrt(math.fsum(value * value for value in vector.dense))
        assert abs(norm - 1.0) <= 1e-3, f"dense 未归一化：{norm}"
        assert all(math.isfinite(value) for value in vector.dense)
        assert vector.sparse, "BGE-M3 必须产出 sparse 词权重"
        assert all(isinstance(token, int) and weight > 0 for token, weight in vector.sparse.items())

    query = provider.embed_query_hybrid("无理由退货怎么计算时间")
    assert len(query.dense) == DENSE_DIMENSION
    assert query.sparse


def test_document_and_query_vectors_are_comparable() -> None:
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    provider = get_bge_m3_provider(get_settings())
    document = provider.embed_documents_hybrid(["退货期限为签收后七日内"])[0]
    related = provider.embed_query_hybrid("退货要几天内申请")
    unrelated = provider.embed_query_hybrid("发票抬头怎么填写")

    def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        return math.fsum(a * b for a, b in zip(left, right, strict=True))

    assert cosine(document.dense, related.dense) > cosine(document.dense, unrelated.dense)
