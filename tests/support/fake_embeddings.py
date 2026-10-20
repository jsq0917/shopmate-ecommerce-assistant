"""Test-only embedding fixtures.

``FakeHybridEmbeddingProvider`` mimics the BGE-M3 contract (1024-d dense, sparse token
weights, L2-normalised) without loading real weights, so unit and integration tests stay
fast and deterministic. Production code never imports this module.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

from shopmate_ecommerce_assistant.rag.embeddings import (
    DENSE_DIMENSION,
    EmbeddingMetadata,
    HybridVector,
    _features,
)


def _token_id(feature: str) -> int:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % 30_000


class FakeHybridEmbeddingProvider:
    """Deterministic dense+sparse encoder for tests."""

    name = "fake-hybrid"

    def __init__(self, dimension: int = DENSE_DIMENSION) -> None:
        self.dimension = dimension
        self.metadata = EmbeddingMetadata(
            model="fake-hybrid",
            provider=self.name,
            dimension=dimension,
            revision="test",
            fingerprint="test-fingerprint",
        )

    def _dense(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimension
        for feature, weight in _features(text):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * (1.0 + math.log(weight) if weight >= 1.0 else weight)
        norm = math.sqrt(math.fsum(value * value for value in vector))
        if norm == 0.0:
            vector[0] = 1.0
            return tuple(vector)
        return tuple(value / norm for value in vector)

    def _sparse(self, text: str) -> dict[int, float]:
        sparse: dict[int, float] = {}
        for feature, weight in _features(text):
            token = _token_id(feature)
            sparse[token] = sparse.get(token, 0.0) + float(weight)
        if not sparse:
            sparse[0] = 1.0
        return dict(sorted(sparse.items()))

    def embed_documents_hybrid(self, texts: Sequence[str]) -> list[HybridVector]:
        return [HybridVector(dense=self._dense(text), sparse=self._sparse(text)) for text in texts]

    def embed_query_hybrid(self, text: str) -> HybridVector:
        return HybridVector(dense=self._dense(text), sparse=self._sparse(text))

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [list(self._dense(text)) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return list(self._dense(text))
