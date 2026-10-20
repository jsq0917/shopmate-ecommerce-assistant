"""Hybrid policy retrieval: BGE-M3 dense + sparse, RRF fusion, authoritative re-check.

Contract (AGENTS.md §10.4, ADR-0002):

* one BGE-M3 forward pass produces the query's dense(1024, L2-normalised) and sparse
  lexical weights;
* both branches are queried in a single Milvus ``hybrid_search`` call — dense top 30 and
  sparse top 30 — fused with RRF (k=60);
* a branch failure raises a specific error and is audited. There is **no silent
  dense-only fallback**; dense-only exists solely as an explicit ablation mode used by
  the retrieval evaluation, and its results are labelled as such;
* fused candidates are re-validated against PostgreSQL (shop, knowledge base, locale,
  region, document/version status, effective window) before they can be cited;
* evidence selection is 4-8 chunks inside a token budget, each with a stable citation.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.db.repositories.knowledge import (
    ChunkMetadata,
    authorization_issues,
    load_chunk_metadata,
)
from shopmate_ecommerce_assistant.rag.citations import (
    Citation,
    EvidenceChunk,
    build_citations,
    detect_version_conflicts,
    select_evidence,
)
from shopmate_ecommerce_assistant.rag.embeddings import (
    EmbeddingMetadata,
    HybridEmbeddingProvider,
)
from shopmate_ecommerce_assistant.rag.errors import (
    IngestionError,
    InvalidEmbeddingError,
    RetrievalError,
)
from shopmate_ecommerce_assistant.rag.milvus_store import MilvusKnowledgeStore
from shopmate_ecommerce_assistant.rag.rerank import NoopReranker, Reranker, build_reranker

logger = logging.getLogger(__name__)


class RetrievalMode(StrEnum):
    """Retrieval path used for one request."""

    HYBRID = "hybrid"
    DENSE_ONLY_ABLATION = "dense_only_ablation"


@dataclass(frozen=True, slots=True)
class RetrievalScope:
    """Tenant and validity scope. Callers may narrow it, never widen it."""

    shop_id: str
    knowledge_base_id: str | None = None
    locale: str | None = "zh-CN"
    region: str | None = "CN"
    at: datetime | None = None
    doc_types: tuple[str, ...] = ()
    status: str = "ready"

    @property
    def moment(self) -> datetime:
        return self.at or datetime.now(UTC)

    def as_dict(self) -> dict[str, Any]:
        return {
            "shop_id": self.shop_id,
            "knowledge_base_id": self.knowledge_base_id,
            "locale": self.locale,
            "region": self.region,
            "at": self.moment.isoformat(),
            "doc_types": list(self.doc_types),
            "status": self.status,
        }


class ChunkAuthorizer(Protocol):
    """Loads authoritative PostgreSQL metadata for candidate chunk ids."""

    async def __call__(self, chunk_ids: Sequence[UUID]) -> dict[UUID, ChunkMetadata]:
        """Return metadata keyed by chunk id; missing ids mean "not authorised"."""


def session_authorizer(session: Any) -> ChunkAuthorizer:
    """Bind an ``AsyncSession`` into an authorizer callable."""

    async def _load(chunk_ids: Sequence[UUID]) -> dict[UUID, ChunkMetadata]:
        return await load_chunk_metadata(session, chunk_ids)

    return _load


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Retrieval output: evidence, citations, conflict flags and the audit record."""

    query: str
    scope: RetrievalScope
    mode: RetrievalMode
    evidence: tuple[EvidenceChunk, ...]
    citations: tuple[Citation, ...]
    evidence_sufficient: bool
    top_dense_similarity: float | None
    conflicts: dict[str, list[str]] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)

    @property
    def has_evidence(self) -> bool:
        return bool(self.evidence)


def _query_digest(query: str) -> str:
    return hashlib.sha256(query.strip().encode("utf-8")).hexdigest()[:16]


def _uuid(value: str | None, *, field_name: str) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise RetrievalError(
            "INVALID_SCOPE", f"检索范围字段 {field_name} 不是合法 UUID", retryable=False
        ) from exc


class DocumentRetriever:
    """Production hybrid retriever for the policy/knowledge path."""

    def __init__(
        self,
        *,
        settings: Settings,
        provider: HybridEmbeddingProvider,
        store: MilvusKnowledgeStore,
        authorizer: ChunkAuthorizer,
        reranker: Reranker | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._store = store
        self._authorize = authorizer
        self._reranker = reranker if reranker is not None else NoopReranker()
        self._clock = clock or (lambda: datetime.now(UTC))

    # -- public API --------------------------------------------------------
    async def retrieve(
        self,
        query: str,
        scope: RetrievalScope,
        *,
        mode: RetrievalMode = RetrievalMode.HYBRID,
    ) -> RetrievalResult:
        """Retrieve citable evidence for ``query`` inside ``scope``."""
        if not query.strip():
            raise RetrievalError("EMPTY_QUERY", "查询为空", retryable=False)
        started = time.perf_counter()
        at = scope.at or self._clock()
        scope = RetrievalScope(
            shop_id=scope.shop_id,
            knowledge_base_id=scope.knowledge_base_id,
            locale=scope.locale,
            region=scope.region,
            at=at,
            doc_types=scope.doc_types,
            status=scope.status,
        )
        audit: dict[str, Any] = {
            "query_digest": _query_digest(query),
            "query_chars": len(query),
            "mode": mode.value,
            "scope": scope.as_dict(),
            "rrf_k": self._settings.retrieval_rrf_k,
            "dense_limit": self._settings.retrieval_dense_limit,
            "sparse_limit": self._settings.retrieval_sparse_limit,
            "candidate_limit": self._settings.retrieval_candidate_limit,
            "reranker": self._reranker.name,
        }

        query_vector = self._embed_query(query, audit)
        expr = self._store.build_filter(
            shop_id=scope.shop_id,
            knowledge_base_id=scope.knowledge_base_id,
            region=scope.region,
            locale=scope.locale,
            doc_types=scope.doc_types or None,
            at=at,
            status=scope.status,
        )
        audit["filter_expr"] = expr

        hits = self._search(query_vector.dense, query_vector.sparse, expr, mode, audit)
        audit["fused_candidates"] = len(hits)

        authorized, rejected = await self._verify(hits, scope)
        audit["rejected"] = rejected

        similarities = self._score(query_vector.dense, authorized, audit)
        ranked = self._rank(query, authorized, similarities, audit, mode=mode)
        # Evaluation needs the *pre-selection* ranking: Recall@k / MRR are defined over the
        # full candidate list, not over the 4-8 chunks that made it into the context window.
        # AGENTS.md §10.4.8 already requires recording both branches' top-k and RRF rank.
        audit["ranked"] = [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "title": chunk.title,
                "version": chunk.version,
                "position": position,
                "rrf_rank": chunk.rrf_rank,
                "dense_similarity": chunk.dense_similarity,
                "branch_support": chunk.branch_support,
            }
            for position, chunk in enumerate(ranked, start=1)
        ]
        selected = select_evidence(
            ranked,
            min_chunks=self._settings.retrieval_min_chunks,
            max_chunks=self._settings.retrieval_max_chunks,
            token_budget=self._settings.retrieval_context_token_budget,
            max_per_document=self._settings.retrieval_max_chunks_per_document,
        )
        citations = build_citations(selected)
        conflicts = detect_version_conflicts(selected)
        top_similarity = (
            max((chunk.dense_similarity or 0.0) for chunk in selected) if selected else None
        )
        sufficient = self._evidence_sufficient(selected, top_similarity)

        audit.update(
            {
                "authorized_candidates": len(authorized),
                "selected": len(selected),
                "selected_chunk_ids": [chunk.chunk_id for chunk in selected],
                "citation_ids": [citation.citation_id for citation in citations],
                "top_dense_similarity": top_similarity,
                "evidence_sufficient": sufficient,
                "conflicts": conflicts,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
        logger.info(
            "knowledge retrieval",
            extra={
                "route": "policy_rag",
                "retrieval_mode": mode.value,
                "shop_id": scope.shop_id,
                "knowledge_base_id": scope.knowledge_base_id,
                "fused_candidates": audit["fused_candidates"],
                "selected": len(selected),
                "latency_ms": audit["latency_ms"],
                "evidence_sufficient": sufficient,
                "embedding_model": audit.get("embedding", {}).get("model"),
            },
        )
        return RetrievalResult(
            query=query,
            scope=scope,
            mode=mode,
            evidence=tuple(selected),
            citations=tuple(citations),
            evidence_sufficient=sufficient,
            top_dense_similarity=top_similarity,
            conflicts=conflicts,
            audit=audit,
        )

    # -- steps -------------------------------------------------------------
    def _embed_query(self, query: str, audit: dict[str, Any]) -> Any:
        try:
            vector = self._provider.embed_query_hybrid(query)
            metadata: EmbeddingMetadata = self._provider.metadata
        except (InvalidEmbeddingError, IngestionError) as exc:
            code = getattr(exc, "code", "QUERY_EMBEDDING_FAILED")
            audit["error"] = {"code": code, "message": getattr(exc, "message", str(exc))}
            raise RetrievalError(
                "QUERY_EMBEDDING_FAILED", f"查询向量生成失败：{code}", retryable=True
            ) from exc
        audit["embedding"] = metadata.as_dict()
        audit["query_sparse_terms"] = len(vector.sparse)
        return vector

    def _search(
        self,
        dense: Sequence[float],
        sparse: Any,
        expr: str,
        mode: RetrievalMode,
        audit: dict[str, Any],
    ) -> list[Any]:
        """Run the retrieval call, attributing failures to the responsible branch."""
        if mode is RetrievalMode.DENSE_ONLY_ABLATION:
            # Explicit ablation: used only by scripts/eval_retrieval.py, never by a
            # user-facing answer path.
            audit["branch"] = {"dense": "ablation_only", "sparse": "disabled_by_request"}
            try:
                return self._store.dense_search(
                    dense, expr=expr, limit=self._settings.retrieval_candidate_limit
                )
            except RetrievalError as exc:
                audit["error"] = {"code": exc.code, "message": exc.message}
                raise
        try:
            fused = self._store.hybrid_search(
                dense,
                sparse,
                expr=expr,
                dense_limit=self._settings.retrieval_dense_limit,
                sparse_limit=self._settings.retrieval_sparse_limit,
                rrf_k=self._settings.retrieval_rrf_k,
                limit=self._settings.retrieval_candidate_limit,
            )
        except RetrievalError as exc:
            code = self._diagnose(dense, sparse, expr, audit, fallback=exc.code)
            audit["error"] = {"code": code, "message": exc.message}
            audit["degraded"] = False
            logger.error(
                "knowledge retrieval failed",
                extra={
                    "route": "policy_rag",
                    "retrieval_mode": mode.value,
                    "error_code": code,
                    "branch": audit.get("branch"),
                    "degraded": False,
                    "dense_limit": self._settings.retrieval_dense_limit,
                    "sparse_limit": self._settings.retrieval_sparse_limit,
                    "rrf_k": self._settings.retrieval_rrf_k,
                },
            )
            raise RetrievalError(code, exc.message, retryable=exc.retryable) from exc
        audit["branch"] = {"dense": "ok", "sparse": "ok"}
        return list(fused.hits)

    def _diagnose(
        self,
        dense: Sequence[float],
        sparse: Any,
        expr: str,
        audit: dict[str, Any],
        *,
        fallback: str,
    ) -> str:
        """Identify which branch broke, without ever returning partial results."""
        branch = {"dense": "ok", "sparse": "ok"}
        code = fallback
        try:
            self._store.dense_search(dense, expr=expr, limit=1)
        except RetrievalError:
            branch["dense"] = "failed"
            code = "DENSE_BRANCH_FAILED"
        try:
            self._store.sparse_search(sparse, expr=expr, limit=1)
        except RetrievalError:
            branch["sparse"] = "failed"
            if code == "DENSE_BRANCH_FAILED":
                code = "BOTH_BRANCHES_FAILED"
            else:
                code = "SPARSE_BRANCH_FAILED"
        audit["branch"] = branch
        audit["degraded"] = False
        return code

    async def _verify(
        self, hits: Sequence[Any], scope: RetrievalScope
    ) -> tuple[list[Any], dict[str, int]]:
        """Re-check every fused candidate against PostgreSQL before it can be cited."""
        valid_ids: list[UUID] = []
        for hit in hits:
            try:
                valid_ids.append(UUID(str(hit.chunk_id)))
            except (TypeError, ValueError):
                continue
        metadata = await self._authorize(valid_ids) if valid_ids else {}
        shop_uuid = _uuid(scope.shop_id, field_name="shop_id")
        kb_uuid = _uuid(scope.knowledge_base_id, field_name="knowledge_base_id")
        if shop_uuid is None:
            raise RetrievalError("INVALID_SCOPE", "shop_id 不能为空", retryable=False)
        allowed: list[Any] = []
        rejected: dict[str, int] = {}
        for hit in hits:
            meta = metadata.get(UUID(str(hit.chunk_id))) if _is_uuid(hit.chunk_id) else None
            if meta is None:
                rejected["metadata_missing"] = rejected.get("metadata_missing", 0) + 1
                continue
            issues = authorization_issues(
                meta,
                shop_id=shop_uuid,
                knowledge_base_id=kb_uuid,
                locale=scope.locale,
                region=scope.region,
                at=scope.moment,
                allowed_doc_types=scope.doc_types or None,
            )
            if issues:
                for issue in issues:
                    rejected[issue] = rejected.get(issue, 0) + 1
                continue
            allowed.append((hit, meta))
        return allowed, rejected

    def _score(
        self, dense: Sequence[float], authorized: Sequence[Any], audit: dict[str, Any]
    ) -> dict[str, float]:
        """Exact cosine similarity for authorised candidates (evidence calibration)."""
        if not authorized:
            return {}
        try:
            similarities = self._store.dense_similarity(
                dense, [str(hit.chunk_id) for hit, _ in authorized]
            )
        except RetrievalError as exc:
            audit["error"] = {"code": exc.code, "message": exc.message}
            raise
        return similarities

    def _rank(
        self,
        query: str,
        authorized: Sequence[Any],
        similarities: dict[str, float],
        audit: dict[str, Any],
        *,
        mode: RetrievalMode,
    ) -> list[EvidenceChunk]:
        """Build evidence chunks in fused order, then optionally rerank."""
        # A fused RRF score is the sum of 1/(k+rank) over the branches that found the
        # chunk, so the score range tells us whether one or both branches matched. The
        # threshold sits between "best single-branch hit" and "worst dual-branch hit".
        k = self._settings.retrieval_rrf_k
        single_branch_max = 1.0 / k
        dual_branch_min = 2.0 / (k + self._settings.retrieval_sparse_limit)
        support_threshold = (single_branch_max + dual_branch_min) / 2.0
        chunks: list[EvidenceChunk] = []
        for rank, (hit, meta) in enumerate(authorized, start=1):
            support = 0
            if mode is not RetrievalMode.DENSE_ONLY_ABLATION:
                support = 2 if float(hit.score) >= support_threshold else 1
            chunks.append(
                EvidenceChunk(
                    chunk_id=str(meta.chunk_id),
                    document_id=str(meta.document_id),
                    version_id=str(meta.version_id),
                    title=meta.title,
                    heading_path=meta.heading_path,
                    page_no=meta.page_no,
                    version=meta.version,
                    effective_from=meta.effective_from,
                    effective_to=meta.effective_to,
                    text=meta.text,
                    token_count=meta.token_count,
                    score=float(hit.score),
                    dense_similarity=similarities.get(str(meta.chunk_id)),
                    rrf_rank=rank,
                    branch_support=support,
                )
            )
        top_n = self._settings.retrieval_candidate_limit
        reranked = self._reranker.rerank(query, chunks, top_n=top_n)
        if self._reranker.name != "none":
            audit["reranked"] = True
        return reranked

    def _evidence_sufficient(
        self, selected: Sequence[EvidenceChunk], top_similarity: float | None
    ) -> bool:
        if not selected:
            return False
        if top_similarity is None:
            return False
        return top_similarity >= self._settings.policy_min_evidence_similarity


def build_retriever(
    settings: Settings,
    *,
    session: Any,
    provider: HybridEmbeddingProvider | None = None,
    store: MilvusKnowledgeStore | None = None,
    reranker: Reranker | None = None,
) -> DocumentRetriever:
    """Construct the production retriever for one database session."""
    from shopmate_ecommerce_assistant.rag.embeddings import get_bge_m3_provider
    from shopmate_ecommerce_assistant.rag.milvus_store import build_store

    return DocumentRetriever(
        settings=settings,
        provider=provider or get_bge_m3_provider(settings),
        store=store or build_store(settings),
        authorizer=session_authorizer(session),
        reranker=reranker if reranker is not None else build_reranker(settings),
    )


def _is_uuid(value: str) -> bool:
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True
