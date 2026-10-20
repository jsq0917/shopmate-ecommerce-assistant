"""Embedding contract: BGE-M3 is the only production provider, dense is normalised."""

from __future__ import annotations

import math

import pytest

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.rag.embeddings import (
    DENSE_DIMENSION,
    BgeM3EmbeddingProvider,
    HashingEmbeddingProvider,
    build_embedding_provider,
    ensure_finite,
    get_bge_m3_provider,
    l2_normalise,
    normalise_text,
    reset_bge_m3_provider,
    to_sparse_weights,
    unit_norm,
)
from shopmate_ecommerce_assistant.rag.errors import (
    EmbeddingConfigError,
    EmbeddingModelUnavailable,
    InvalidEmbeddingError,
)
from tests.support.fake_embeddings import FakeHybridEmbeddingProvider


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


# -- provider selection ----------------------------------------------------


def test_production_factory_returns_bge_m3() -> None:
    reset_bge_m3_provider()
    provider = build_embedding_provider(_settings())
    try:
        assert isinstance(provider, BgeM3EmbeddingProvider)
        assert provider.name == "bge-m3"
        assert provider.dimension == DENSE_DIMENSION
        assert not isinstance(provider, HashingEmbeddingProvider)
    finally:
        reset_bge_m3_provider()


def test_provider_is_a_process_singleton() -> None:
    reset_bge_m3_provider()
    settings = _settings()
    try:
        first = get_bge_m3_provider(settings)
        second = get_bge_m3_provider(settings)
        assert first is second, "BGE-M3 必须单例加载，避免多个 worker 各占一份权重"
    finally:
        reset_bge_m3_provider()


def test_dimension_other_than_1024_is_rejected() -> None:
    with pytest.raises(EmbeddingConfigError):
        BgeM3EmbeddingProvider(_settings(embedding_dimension=384))


def test_missing_model_path_is_reported() -> None:
    provider = BgeM3EmbeddingProvider(_settings(embedding_model_path="/nonexistent/bge-m3"))
    with pytest.raises(EmbeddingModelUnavailable):
        _ = provider.model_reference


# -- dense validation ------------------------------------------------------


def test_l2_normalise_produces_unit_norm() -> None:
    vector = l2_normalise([3.0, 4.0] + [0.0] * (DENSE_DIMENSION - 2), dimension=DENSE_DIMENSION)
    assert unit_norm(vector)
    assert math.isclose(vector[0], 0.6)


def test_non_finite_values_are_rejected() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        values = [0.0] * DENSE_DIMENSION
        values[0] = bad
        with pytest.raises(InvalidEmbeddingError) as excinfo:
            l2_normalise(values, dimension=DENSE_DIMENSION)
        assert excinfo.value.code == "EMBEDDING_NON_FINITE"
        assert excinfo.value.retryable is True


def test_ensure_finite_accepts_normal_values() -> None:
    ensure_finite([0.0, 0.5, -0.5], context="test")


def test_zero_vector_is_rejected() -> None:
    with pytest.raises(InvalidEmbeddingError) as excinfo:
        l2_normalise([0.0] * DENSE_DIMENSION, dimension=DENSE_DIMENSION)
    assert excinfo.value.code == "EMBEDDING_ZERO_VECTOR"


def test_dimension_mismatch_is_rejected() -> None:
    with pytest.raises(InvalidEmbeddingError) as excinfo:
        l2_normalise([1.0, 0.0, 0.0], dimension=DENSE_DIMENSION)
    assert excinfo.value.code == "EMBEDDING_DIMENSION_MISMATCH"


# -- sparse ----------------------------------------------------------------


def test_sparse_weights_convert_token_ids_and_drop_non_positive() -> None:
    sparse = to_sparse_weights({"12": 0.5, "7": 0.25, "9": 0.0, "11": -1.0})
    assert sparse == {7: 0.25, 12: 0.5}
    assert list(sparse) == sorted(sparse)


def test_sparse_rejects_non_numeric_keys() -> None:
    with pytest.raises(InvalidEmbeddingError) as excinfo:
        to_sparse_weights({"退货": 0.5})
    assert excinfo.value.code == "EMBEDDING_SPARSE_KEY"


# -- fixtures --------------------------------------------------------------


def test_hashing_provider_is_deterministic_and_normalised() -> None:
    provider = HashingEmbeddingProvider(dimension=128)
    first = provider.embed_query("七天无理由退货政策")
    second = provider.embed_query("七天无理由退货政策")
    assert first == second
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0, rel_tol=1e-6)


def test_hashing_provider_rejects_invalid_dimension() -> None:
    with pytest.raises(ValueError):
        HashingEmbeddingProvider(dimension=0)


def test_normalize_text_collapses_whitespace() -> None:
    assert normalise_text("  退货\t政策  ") == "退货 政策"


def test_fake_hybrid_provider_satisfies_the_contract() -> None:
    provider = FakeHybridEmbeddingProvider()
    batch = provider.embed_documents_hybrid(["退货政策", "退款时效"])
    query = provider.embed_query_hybrid("退货政策")
    assert len(batch) == 2
    assert all(len(item.dense) == DENSE_DIMENSION for item in batch)
    assert all(item.sparse for item in batch), "sparse 不得为空"
    assert unit_norm(query.dense)
    assert provider.metadata.dimension == DENSE_DIMENSION
