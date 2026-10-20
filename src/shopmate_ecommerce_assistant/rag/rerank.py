"""Optional reranking hook for retrieved policy chunks.

The MVP ships reranking **disabled**. The interface exists so a BGE reranker (or a hosted
one) can be added without touching retrieval, and the factory fails loudly when
``RERANKER_ENABLED`` is turned on without a registered provider instead of pretending to
rerank.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.rag.citations import EvidenceChunk
from shopmate_ecommerce_assistant.rag.errors import RetrievalError


@runtime_checkable
class Reranker(Protocol):
    """Reorders candidate chunks with a cross-encoder or equivalent model."""

    name: str

    def rerank(
        self, query: str, chunks: Sequence[EvidenceChunk], *, top_n: int
    ) -> list[EvidenceChunk]:
        """Return at most ``top_n`` chunks in descending relevance."""


class NoopReranker:
    """Pass-through reranker used when reranking is disabled (the default)."""

    name = "none"

    def rerank(
        self, query: str, chunks: Sequence[EvidenceChunk], *, top_n: int
    ) -> list[EvidenceChunk]:
        """Keep the RRF order and truncate."""
        return list(chunks[:top_n])


def build_reranker(settings: Settings) -> Reranker:
    """Return the configured reranker.

    Only the no-op implementation exists today. Enabling reranking without registering a
    provider raises ``RERANKER_NOT_CONFIGURED`` so retrieval never claims a rerank happened.
    """
    if not settings.reranker_enabled:
        return NoopReranker()
    raise RetrievalError(
        "RERANKER_NOT_CONFIGURED",
        "已开启 reranker，但项目内尚未注册重排实现；请关闭 RERANKER_ENABLED 或先接入模型",
        retryable=False,
    )
