"""Milvus collection management and vector I/O for knowledge chunks.

Stage 7 schema: every row carries a **1024-dimensional dense vector** (COSINE) and a
**sparse lexical vector** (IP) produced by the same BGE-M3 forward pass. Both indexes are
mandatory — a row without sparse weights is rejected at write time, and the collection is
verified on open so a stage-5 dense-only collection cannot be silently reused.

One row = one *child* chunk. Parent chunks stay in PostgreSQL and are expanded when
building citations.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pymilvus import AnnSearchRequest, DataType, MilvusClient, RRFRanker

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.rag.embeddings import unit_norm
from shopmate_ecommerce_assistant.rag.errors import (
    CollectionSchemaMismatch,
    InvalidEmbeddingError,
    RetrievalError,
    VectorStoreUnavailable,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2
DENSE_FIELD = "dense_vector"
SPARSE_FIELD = "sparse_vector"
DENSE_METRIC = "COSINE"
SPARSE_METRIC = "IP"
TEXT_MAX_LENGTH = 8192
HEADING_MAX_LENGTH = 1024
METADATA_MAX_LENGTH = 4096
MODEL_MAX_LENGTH = 64
OUTPUT_FIELDS = [
    "chunk_id",
    "shop_id",
    "knowledge_base_id",
    "document_id",
    "version_id",
    "doc_type",
    "locale",
    "region",
    "status",
    "page_no",
    "heading_path",
    "text",
    "metadata_json",
    "embedding_model",
]


@dataclass(frozen=True, slots=True)
class ChunkVector:
    """A single child chunk ready for insertion (dense + sparse)."""

    chunk_id: str
    shop_id: str
    knowledge_base_id: str
    document_id: str
    version_id: str
    doc_type: str
    locale: str
    region: str
    status: str
    effective_from: datetime
    effective_to: datetime | None
    page_no: int | None
    heading_path: tuple[str, ...]
    text: str
    metadata_json: str
    dense: tuple[float, ...] = ()
    sparse: Mapping[int, float] = field(default_factory=dict)
    embedding_model: str = "bge-m3"
    is_enabled: bool = True


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A retrieval hit with its applied metadata."""

    chunk_id: str
    score: float
    text: str
    document_id: str
    version_id: str
    knowledge_base_id: str
    doc_type: str
    page_no: int | None
    heading_path: tuple[str, ...]
    embedding_model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
    """Fused result plus the configuration that produced it (for audit)."""

    hits: tuple[SearchHit, ...]
    dense_limit: int
    sparse_limit: int
    rrf_k: int


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _epoch_seconds(value: datetime) -> int:
    return int(value.astimezone(UTC).timestamp())


class MilvusKnowledgeStore:
    """Thin, typed wrapper around ``MilvusClient`` for the knowledge collection."""

    def __init__(self, settings: Settings, *, client: MilvusClient | None = None) -> None:
        self.collection = settings.milvus_collection
        self.dimension = settings.embedding_dimension
        self.timeout = settings.milvus_timeout_seconds
        self._uri = settings.milvus_uri
        self._client = client

    # -- lifecycle ---------------------------------------------------------
    @property
    def uri(self) -> str:
        """Return the configured Milvus endpoint (no credentials are stored here)."""
        return self._uri

    @property
    def client(self) -> MilvusClient:
        if self._client is None:
            try:
                self._client = MilvusClient(uri=self._uri, timeout=self.timeout)
            except Exception as exc:  # pragma: no cover - driver-specific
                raise VectorStoreUnavailable("无法建立 Milvus 连接") from exc
        return self._client

    def close(self) -> None:
        """Close the underlying client if it was opened."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # pragma: no cover - best effort cleanup
                logger.warning("milvus client close failed", exc_info=True)
            self._client = None

    def ping(self) -> bool:
        """Return True when the collection exists and is queryable."""
        try:
            return bool(self.client.has_collection(self.collection))
        except Exception:
            return False

    def describe(self) -> dict[str, Any]:
        """Return field names, dense dimension, index types and row count."""
        try:
            described = self.client.describe_collection(self.collection)
            indexes = self.client.list_indexes(self.collection)
            index_info = {
                name: self.client.describe_index(self.collection, name) for name in indexes
            }
        except Exception as exc:
            raise VectorStoreUnavailable("读取 collection 结构失败") from exc
        fields = {item["name"]: item for item in described.get("fields", [])}
        dense_dim = int(fields.get(DENSE_FIELD, {}).get("params", {}).get("dim", 0) or 0)
        return {
            "collection": self.collection,
            "fields": sorted(fields),
            "dense_dimension": dense_dim,
            "has_sparse": SPARSE_FIELD in fields,
            "indexes": index_info,
        }

    def assert_compatible(self) -> dict[str, Any]:
        """Fail fast when the collection cannot serve the BGE-M3 hybrid schema."""
        described = self.describe()
        fields = set(described["fields"])
        missing = {DENSE_FIELD, SPARSE_FIELD, "embedding_model"} - fields
        if missing:
            raise CollectionSchemaMismatch(
                f"缺少字段 {sorted(missing)}（阶段 5 的 dense-only collection 必须重建）"
            )
        if described["dense_dimension"] != self.dimension:
            raise CollectionSchemaMismatch(
                f"dense 维度为 {described['dense_dimension']}，期望 {self.dimension}"
            )
        indexes = set(described["indexes"])
        if DENSE_FIELD not in indexes or SPARSE_FIELD not in indexes:
            raise CollectionSchemaMismatch("dense 与 sparse 必须同时建立索引")
        return described

    def ensure_collection(self) -> None:
        """Create the collection with both indexes, or validate the existing one."""
        try:
            if self.client.has_collection(self.collection):
                self.assert_compatible()
                self.client.load_collection(self.collection)
                return
            schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64)
            for name, max_length in (
                ("shop_id", 64),
                ("knowledge_base_id", 64),
                ("document_id", 64),
                ("version_id", 64),
                ("doc_type", 32),
                ("locale", 16),
                ("region", 8),
                ("status", 16),
                ("embedding_model", MODEL_MAX_LENGTH),
            ):
                schema.add_field(name, DataType.VARCHAR, max_length=max_length)
            schema.add_field("is_enabled", DataType.BOOL)
            schema.add_field("effective_from", DataType.INT64)
            schema.add_field("effective_to", DataType.INT64)
            schema.add_field("page_no", DataType.INT64)
            schema.add_field("heading_path", DataType.VARCHAR, max_length=HEADING_MAX_LENGTH)
            schema.add_field("text", DataType.VARCHAR, max_length=TEXT_MAX_LENGTH)
            schema.add_field("metadata_json", DataType.VARCHAR, max_length=METADATA_MAX_LENGTH)
            schema.add_field(DENSE_FIELD, DataType.FLOAT_VECTOR, dim=self.dimension)
            schema.add_field(SPARSE_FIELD, DataType.SPARSE_FLOAT_VECTOR)

            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name=DENSE_FIELD, index_type="AUTOINDEX", metric_type=DENSE_METRIC
            )
            index_params.add_index(
                field_name=SPARSE_FIELD,
                index_type="SPARSE_INVERTED_INDEX",
                metric_type=SPARSE_METRIC,
                params={"inverted_index_algo": "DAAT_MAXSCORE"},
            )
            self.client.create_collection(
                collection_name=self.collection,
                schema=schema,
                index_params=index_params,
            )
            self.client.load_collection(self.collection)
            logger.info(
                "created milvus collection %s (schema v%s)", self.collection, SCHEMA_VERSION
            )
        except CollectionSchemaMismatch:
            raise
        except Exception as exc:
            raise VectorStoreUnavailable("初始化 collection 失败") from exc

    def drop_collection(self) -> None:
        """Delete the collection and its vectors (explicit, destructive)."""
        try:
            if self.client.has_collection(self.collection):
                self.client.drop_collection(self.collection)
                logger.warning("dropped milvus collection %s", self.collection)
        except Exception as exc:
            raise VectorStoreUnavailable("删除 collection 失败") from exc

    # -- writes ------------------------------------------------------------
    def upsert_chunks(self, chunks: Sequence[ChunkVector]) -> int:
        """Insert child chunks; returns the number of written rows."""
        if not chunks:
            return 0
        rows: list[dict[str, Any]] = []
        for chunk in chunks:
            if len(chunk.text) > TEXT_MAX_LENGTH:
                raise VectorStoreUnavailable("片段长度超过向量库字段上限")
            if len(chunk.dense) != self.dimension:
                raise InvalidEmbeddingError(
                    "EMBEDDING_DIMENSION_MISMATCH",
                    f"向量维度 {len(chunk.dense)} 与 collection 维度 {self.dimension} 不一致",
                    retryable=False,
                )
            if not chunk.sparse:
                raise InvalidEmbeddingError(
                    "EMBEDDING_EMPTY_SPARSE", "sparse 向量为空，拒绝写入（双向量必须同时存在）"
                )
            # Normalisation is the provider's job; here we only refuse. A non-unit vector
            # would make COSINE scores incomparable with the query side, so the whole batch
            # is rejected before a single row is written.
            if not unit_norm(chunk.dense):
                norm = math.sqrt(math.fsum(value * value for value in chunk.dense))
                raise InvalidEmbeddingError(
                    "EMBEDDING_NORM_INVALID",
                    f"dense 向量范数为 {norm:.6f}（容差 1e-3），拒绝写入",
                    retryable=False,
                )
            rows.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "shop_id": chunk.shop_id,
                    "knowledge_base_id": chunk.knowledge_base_id,
                    "document_id": chunk.document_id,
                    "version_id": chunk.version_id,
                    "doc_type": chunk.doc_type,
                    "locale": chunk.locale,
                    "region": chunk.region,
                    "status": chunk.status,
                    "embedding_model": chunk.embedding_model,
                    "is_enabled": chunk.is_enabled,
                    "effective_from": _epoch_seconds(chunk.effective_from),
                    "effective_to": (
                        _epoch_seconds(chunk.effective_to) if chunk.effective_to else 0
                    ),
                    "page_no": chunk.page_no or 0,
                    "heading_path": "/".join(chunk.heading_path)[:HEADING_MAX_LENGTH],
                    "text": chunk.text,
                    "metadata_json": chunk.metadata_json[:METADATA_MAX_LENGTH],
                    DENSE_FIELD: list(chunk.dense),
                    SPARSE_FIELD: dict(chunk.sparse),
                }
            )
        try:
            self.ensure_collection()
            self.client.upsert(collection_name=self.collection, data=rows)
            self._flush()
        except (VectorStoreUnavailable, InvalidEmbeddingError, CollectionSchemaMismatch):
            raise
        except Exception as exc:
            raise VectorStoreUnavailable("写入向量失败") from exc
        return len(rows)

    def delete_version(self, version_id: str) -> None:
        """Remove every vector belonging to a version (used before reindex/failure)."""
        try:
            if not self.client.has_collection(self.collection):
                return
            self.client.delete(
                collection_name=self.collection, filter=f'version_id == "{_escape(version_id)}"'
            )
            self._flush()
        except Exception as exc:
            raise VectorStoreUnavailable("删除版本向量失败") from exc

    def _flush(self) -> None:
        try:
            self.client.flush(self.collection)
        except Exception:  # pragma: no cover - flush is best effort
            logger.debug("milvus flush failed", exc_info=True)

    def flush(self) -> None:
        """Flush pending inserts so counts and scans see the latest rows."""
        self._flush()

    # -- filters -----------------------------------------------------------
    def build_filter(
        self,
        *,
        shop_id: str,
        knowledge_base_id: str | None = None,
        region: str | None = None,
        locale: str | None = None,
        doc_types: Sequence[str] | None = None,
        at: datetime | None = None,
        status: str = "ready",
        is_enabled: bool = True,
    ) -> str:
        """Build the tenant/validity expression pushed down into Milvus.

        This is the first of two enforcement layers: PostgreSQL is re-checked after the
        fused ranking, because a vector index is not an authority on permissions.
        """
        clauses = [f'shop_id == "{_escape(shop_id)}"']
        if is_enabled:
            clauses.append("is_enabled == true")
        if status:
            clauses.append(f'status == "{_escape(status)}"')
        if knowledge_base_id:
            clauses.append(f'knowledge_base_id == "{_escape(knowledge_base_id)}"')
        if region:
            clauses.append(f'region == "{_escape(region)}"')
        if locale:
            clauses.append(f'locale == "{_escape(locale)}"')
        if doc_types:
            joined = ", ".join(f'"{_escape(item)}"' for item in doc_types)
            clauses.append(f"doc_type in [{joined}]")
        moment = _epoch_seconds(at or datetime.now(UTC))
        clauses.append(f"effective_from <= {moment}")
        clauses.append(f"(effective_to == 0 or effective_to > {moment})")
        return " and ".join(clauses)

    # -- reads -------------------------------------------------------------
    def hybrid_search(
        self,
        dense: Sequence[float],
        sparse: Mapping[int, float],
        *,
        expr: str,
        dense_limit: int,
        sparse_limit: int,
        rrf_k: int,
        limit: int,
    ) -> HybridSearchResult:
        """Run dense + sparse in one `hybrid_search` call fused by RRF.

        Both branches are mandatory. A failure raises ``RetrievalError`` — the caller
        diagnoses which branch broke and reports it; it must never fall back to dense-only.
        """
        if len(dense) != self.dimension:
            raise InvalidEmbeddingError(
                "EMBEDDING_DIMENSION_MISMATCH",
                f"查询向量维度 {len(dense)} 与 collection 维度 {self.dimension} 不一致",
                retryable=False,
            )
        if not sparse:
            raise RetrievalError("SPARSE_QUERY_EMPTY", "查询未产出 sparse 权重，无法执行混合检索")
        try:
            self.ensure_collection()
            requests = [
                AnnSearchRequest(
                    data=[list(dense)],
                    anns_field=DENSE_FIELD,
                    param={"metric_type": DENSE_METRIC, "params": {}},
                    limit=dense_limit,
                    expr=expr,
                ),
                AnnSearchRequest(
                    data=[dict(sparse)],
                    anns_field=SPARSE_FIELD,
                    param={"metric_type": SPARSE_METRIC, "params": {}},
                    limit=sparse_limit,
                    expr=expr,
                ),
            ]
            raw = self.client.hybrid_search(
                collection_name=self.collection,
                reqs=requests,
                ranker=RRFRanker(k=rrf_k),
                limit=limit,
                output_fields=OUTPUT_FIELDS,
            )
        except (RetrievalError, InvalidEmbeddingError, CollectionSchemaMismatch):
            raise
        except Exception as exc:
            raise RetrievalError("HYBRID_SEARCH_FAILED", "混合检索失败") from exc
        return HybridSearchResult(
            hits=tuple(self._to_hits(raw)),
            dense_limit=dense_limit,
            sparse_limit=sparse_limit,
            rrf_k=rrf_k,
        )

    def dense_search(
        self,
        dense: Sequence[float],
        *,
        expr: str,
        limit: int,
    ) -> list[SearchHit]:
        """Dense-only search. **Ablation / diagnostics only — never used to answer.**"""
        try:
            self.ensure_collection()
            raw = self.client.search(
                collection_name=self.collection,
                data=[list(dense)],
                anns_field=DENSE_FIELD,
                search_params={"metric_type": DENSE_METRIC, "params": {}},
                limit=limit,
                filter=expr,
                output_fields=OUTPUT_FIELDS,
            )
        except (RetrievalError, CollectionSchemaMismatch):
            raise
        except Exception as exc:
            raise RetrievalError("DENSE_BRANCH_FAILED", "dense 检索失败") from exc
        return self._to_hits(raw)

    def sparse_search(
        self,
        sparse: Mapping[int, float],
        *,
        expr: str,
        limit: int,
    ) -> list[SearchHit]:
        """Sparse-only search, used to attribute a hybrid failure to the right branch."""
        if not sparse:
            raise RetrievalError("SPARSE_QUERY_EMPTY", "查询未产出 sparse 权重")
        try:
            self.ensure_collection()
            raw = self.client.search(
                collection_name=self.collection,
                data=[dict(sparse)],
                anns_field=SPARSE_FIELD,
                search_params={"metric_type": SPARSE_METRIC, "params": {}},
                limit=limit,
                filter=expr,
                output_fields=OUTPUT_FIELDS,
            )
        except (RetrievalError, CollectionSchemaMismatch):
            raise
        except Exception as exc:
            raise RetrievalError("SPARSE_BRANCH_FAILED", "sparse 检索失败") from exc
        return self._to_hits(raw)

    def dense_similarity(
        self, dense: Sequence[float], chunk_ids: Sequence[str]
    ) -> dict[str, float]:
        """Return exact cosine similarity for already-known chunks.

        Used for evidence calibration after fusion: the query vector is reused, so this
        costs one small filtered search instead of re-embedding candidate texts.
        """
        if not chunk_ids:
            return {}
        joined = ", ".join(f'"{_escape(chunk_id)}"' for chunk_id in chunk_ids)
        try:
            self.ensure_collection()
            raw = self.client.search(
                collection_name=self.collection,
                data=[list(dense)],
                anns_field=DENSE_FIELD,
                search_params={"metric_type": DENSE_METRIC, "params": {}},
                limit=len(chunk_ids),
                filter=f"chunk_id in [{joined}]",
                output_fields=["chunk_id"],
            )
        except Exception as exc:
            raise RetrievalError("EVIDENCE_SCORING_FAILED", "证据相似度计算失败") from exc
        scores: dict[str, float] = {}
        for row in raw[0] if raw else []:
            entity = dict(row.get("entity") or {})
            chunk_id = str(entity.get("chunk_id") or row.get("id") or "")
            if chunk_id:
                scores[chunk_id] = float(row.get("distance", 0.0))
        return scores

    def _to_hits(self, raw: Any) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for row in raw[0] if raw else []:
            entity: dict[str, Any] = dict(row.get("entity") or {})
            heading = str(entity.get("heading_path") or "")
            page_no = int(entity.get("page_no") or 0)
            hits.append(
                SearchHit(
                    chunk_id=str(entity.get("chunk_id") or row.get("id")),
                    score=float(row.get("distance", 0.0)),
                    text=str(entity.get("text") or ""),
                    document_id=str(entity.get("document_id") or ""),
                    version_id=str(entity.get("version_id") or ""),
                    knowledge_base_id=str(entity.get("knowledge_base_id") or ""),
                    doc_type=str(entity.get("doc_type") or ""),
                    page_no=page_no or None,
                    heading_path=tuple(part for part in heading.split("/") if part),
                    embedding_model=str(entity.get("embedding_model") or ""),
                    metadata={
                        "region": entity.get("region"),
                        "locale": entity.get("locale"),
                        "status": entity.get("status"),
                        "shop_id": entity.get("shop_id"),
                        "metadata_json": entity.get("metadata_json"),
                    },
                )
            )
        return hits

    def count(self, expr: str = "") -> int:
        """Count rows matching an expression (empty expression counts everything)."""
        try:
            self.ensure_collection()
            result = self.client.query(
                collection_name=self.collection,
                filter=expr,
                output_fields=["count(*)"],
            )
        except Exception as exc:
            raise VectorStoreUnavailable("统计向量失败") from exc
        if not result:
            return 0
        return int(result[0].get("count(*)", 0))

    def count_version(self, version_id: str) -> int:
        """Count indexed children for one version."""
        return self.count(f'version_id == "{_escape(version_id)}"')

    def iter_vectors(
        self, *, batch_size: int = 200, expr: str = ""
    ) -> Iterable[list[dict[str, Any]]]:
        """Yield raw rows including both vector fields (verification scripts only)."""
        total = self.count(expr)
        offset = 0
        while offset < total:
            try:
                rows = self.client.query(
                    collection_name=self.collection,
                    filter=expr or 'chunk_id != ""',
                    output_fields=["chunk_id", DENSE_FIELD, SPARSE_FIELD, "embedding_model"],
                    limit=batch_size,
                    offset=offset,
                )
            except Exception as exc:
                raise VectorStoreUnavailable("读取向量失败") from exc
            if not rows:
                break
            yield list(rows)
            offset += len(rows)


def _sparse_weight_count(value: Any) -> int:
    """Count non-zero entries of a sparse vector returned by Milvus."""
    if value is None:
        return 0
    if isinstance(value, Mapping):
        return sum(1 for weight in value.values() if float(weight) > 0.0)
    if isinstance(value, (list, tuple)):
        return len(value)
    return 0


def collect_vector_stats(
    store: MilvusKnowledgeStore, *, batch_size: int = 200, expr: str = ""
) -> dict[str, Any]:
    """Summarise integrity of the collection: dimension, sparse coverage, norm.

    Verification is part of the deliverable: "sparse 非空率 100%", "dense 维度 1024" and
    "范数≈1" are measured here rather than assumed.
    """
    total = 0
    sparse_non_empty = 0
    dims: set[int] = set()
    bad_norms = 0
    min_norm = math.inf
    max_norm = -math.inf
    models: dict[str, int] = {}
    for rows in store.iter_vectors(batch_size=batch_size, expr=expr):
        for row in rows:
            total += 1
            dense = row.get(DENSE_FIELD) or []
            dims.add(len(dense))
            norm = math.sqrt(math.fsum(float(value) * float(value) for value in dense))
            min_norm = min(min_norm, norm)
            max_norm = max(max_norm, norm)
            if abs(norm - 1.0) > 1e-3:
                bad_norms += 1
            if _sparse_weight_count(row.get(SPARSE_FIELD)) > 0:
                sparse_non_empty += 1
            model = str(row.get("embedding_model") or "")
            models[model] = models.get(model, 0) + 1
    return {
        "collection": store.collection,
        "rows": total,
        "dense_dimensions": sorted(dims),
        "sparse_non_empty": sparse_non_empty,
        "sparse_coverage": (sparse_non_empty / total) if total else 0.0,
        "norms_outside_tolerance": bad_norms,
        "min_norm": None if total == 0 else round(min_norm, 6),
        "max_norm": None if total == 0 else round(max_norm, 6),
        "embedding_models": models,
    }


def build_store(settings: Settings) -> MilvusKnowledgeStore:
    """Construct a store from settings (no network I/O until first use)."""
    return MilvusKnowledgeStore(settings)
