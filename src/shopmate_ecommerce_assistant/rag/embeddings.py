"""Embedding providers.

Stage 7 fixes the embedding contract: **one local BGE-M3 model produces both the dense
vector and the sparse lexical weights in a single forward pass**. The dense vector is
1024-dimensional and L2-normalised on write *and* query; the sparse vector is a
``{token_id: weight}`` dictionary consumed by Milvus ``SPARSE_FLOAT_VECTOR`` (metric IP).

``HashingEmbeddingProvider`` is kept deliberately: it is a deterministic, dependency-free
encoder used only by unit tests and by stage-5 artefacts. It must never be selected by the
production factory (``build_embedding_provider``), and it does not emit sparse vectors, so
it cannot silently replace BGE-M3 in the hybrid path.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import struct
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.rag.chunking import is_cjk
from shopmate_ecommerce_assistant.rag.errors import (
    EmbeddingConfigError,
    EmbeddingModelUnavailable,
    InvalidEmbeddingError,
)

DENSE_DIMENSION = 1024
SPARSE_KIND = "bge-m3-lexical"
LATIN_WORD = re.compile(r"[a-z0-9]+")
WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class EmbeddingMetadata:
    """Audit record describing *which* model produced a vector.

    Persisted in ``knowledge_chunks.metadata_jsonb['embedding']`` and in the retrieval
    audit so a later re-import can prove the collection was built with the same weights.
    """

    model: str
    provider: str
    dimension: int
    revision: str
    fingerprint: str
    dense_normalized: bool = True
    sparse: str = SPARSE_KIND

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "model": self.model,
            "provider": self.provider,
            "dimension": self.dimension,
            "revision": self.revision,
            "fingerprint": self.fingerprint,
            "dense_normalized": self.dense_normalized,
            "sparse": self.sparse,
        }


@dataclass(frozen=True, slots=True)
class HybridVector:
    """Dense + sparse output for one text."""

    dense: tuple[float, ...]
    sparse: dict[int, float]


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Minimal dense contract (kept for fixtures and legacy helpers)."""

    name: str
    dimension: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of chunk texts."""

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""


@runtime_checkable
class HybridEmbeddingProvider(Protocol):
    """Dense + sparse contract required by the hybrid retrieval path."""

    name: str
    dimension: int
    metadata: EmbeddingMetadata

    def embed_documents_hybrid(self, texts: Sequence[str]) -> list[HybridVector]:
        """Embed chunk texts into dense and sparse vectors."""

    def embed_query_hybrid(self, text: str) -> HybridVector:
        """Embed one query into dense and sparse vectors."""


# -- validation helpers ----------------------------------------------------


def ensure_finite(values: Sequence[float], *, context: str) -> None:
    """Reject NaN/Inf before anything reaches the index or the query path."""
    for value in values:
        if not math.isfinite(value):
            raise InvalidEmbeddingError(
                "EMBEDDING_NON_FINITE", f"{context} 出现 NaN/Inf，已拒绝写入"
            )


def l2_normalise(values: Sequence[float], *, dimension: int) -> tuple[float, ...]:
    """L2-normalise a dense vector, rejecting zero and non-finite vectors."""
    if len(values) != dimension:
        raise InvalidEmbeddingError(
            "EMBEDDING_DIMENSION_MISMATCH", f"向量维度 {len(values)} 与期望 {dimension} 不一致"
        )
    ensure_finite(values, context="dense vector")
    norm = math.sqrt(math.fsum(value * value for value in values))
    if norm == 0.0:
        raise InvalidEmbeddingError("EMBEDDING_ZERO_VECTOR", "dense 向量为零向量，无法归一化")
    return tuple(value / norm for value in values)


def unit_norm(values: Sequence[float], *, tolerance: float = 1e-3) -> bool:
    """Return True when ``values`` is already L2-normalised."""
    norm = math.sqrt(math.fsum(value * value for value in values))
    return abs(norm - 1.0) <= tolerance


class HashingEmbeddingProvider:
    """Deterministic hashing encoder — **test fixture only**.

    This is not a semantic model and produces no sparse vector. It exists so unit and
    integration tests can exercise storage and wiring without a 2GB download. The
    production factory never returns it.
    """

    name = "hashing-v1"

    def __init__(self, dimension: int = 384) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        weights: dict[str, float] = {}
        for feature, weight in _features(text):
            weights[feature] = weights.get(feature, 0.0) + weight
        if not weights:
            return vector
        for feature, weight in weights.items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            magnitude = 1.0 + math.log(weight) if weight >= 1.0 else weight
            vector[index] += sign * magnitude
        norm = math.sqrt(math.fsum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed documents in order; output length always equals input length."""
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """Embed a query with the same feature space as documents."""
        return self._embed(text)


def normalise_text(text: str) -> str:
    """Normalise text before feature extraction so formatting differences do not matter."""
    return WHITESPACE.sub(" ", text).strip().lower()


def _features(text: str) -> list[tuple[str, float]]:
    """Extract weighted lexical features that work for Chinese and latin text."""
    normalized = normalise_text(text)
    features: list[tuple[str, float]] = []
    cjk_chars = [char for char in normalized if is_cjk(char)]
    for char in cjk_chars:
        features.append((f"u:{char}", 0.5))
    for left, right in zip(cjk_chars, cjk_chars[1:], strict=False):
        features.append((f"b:{left}{right}", 1.0))
    for word in LATIN_WORD.findall(normalized):
        features.append((f"w:{word}", 1.0))
    return features


# -- BGE-M3 ----------------------------------------------------------------


def _weight_fingerprint(model: Any) -> str:
    """Hash model weights cheaply but deterministically.

    Full-file hashing of ~2GB on every cold start is wasteful, so every parameter
    contributes its name, shape, dtype and a fixed sample of values. Any real weight
    change (or a different conversion/quantisation) alters the digest, which is exactly
    what an "are these vectors from the same weights?" check needs.
    """
    try:
        state = model.model.state_dict()
    except AttributeError:  # pragma: no cover - defensive for unexpected wrappers
        return "unknown"
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name]
        try:
            flat = tensor.detach().reshape(-1).float()
            head = flat[:8].tolist()
            tail = flat[-8:].tolist() if flat.numel() > 8 else []
            shape = tuple(tensor.shape)
        except Exception:  # pragma: no cover - non-tensor entries
            continue
        payload = struct.pack(f"<{len(head)}f", *head) + struct.pack(f"<{len(tail)}f", *tail)
        digest.update(name.encode("utf-8"))
        digest.update(repr(shape).encode("utf-8"))
        digest.update(payload)
    return digest.hexdigest()[:32]


def to_sparse_weights(weights: Mapping[str, float] | None) -> dict[int, float]:
    """Convert BGE-M3 lexical weights (string token ids) into a Milvus sparse dict."""
    if not weights:
        return {}
    sparse: dict[int, float] = {}
    for key, value in weights.items():
        weight = float(value)
        if not math.isfinite(weight) or weight <= 0.0:
            continue
        try:
            token_id = int(key)
        except (TypeError, ValueError) as exc:
            raise InvalidEmbeddingError(
                "EMBEDDING_SPARSE_KEY", "sparse 权重包含非 token id 键"
            ) from exc
        if token_id < 0:
            raise InvalidEmbeddingError("EMBEDDING_SPARSE_KEY", "sparse token id 不能为负")
        sparse[token_id] = weight
    return dict(sorted(sparse.items()))


class BgeM3EmbeddingProvider:
    """Local ``BAAI/bge-m3`` provider: one forward pass, dense + sparse.

    Loading is lazy, process-wide single-instance (see ``get_bge_m3_provider``) and can
    run fully offline when ``embedding_model_path`` points at a mounted weight directory.
    """

    name = "bge-m3"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.dimension = settings.embedding_dimension
        if self.dimension != DENSE_DIMENSION:
            raise EmbeddingConfigError(
                f"BGE-M3 dense 维度固定为 {DENSE_DIMENSION}，当前配置为 {self.dimension}"
            )
        self._model: Any | None = None
        self._metadata: EmbeddingMetadata | None = None
        self._load_lock = threading.Lock()
        self._encode_lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    @property
    def model_reference(self) -> str:
        """Return the local weight path when configured, else the hub model name."""
        path = self._settings.embedding_model_path.strip()
        if path:
            resolved = Path(path).expanduser()
            if not resolved.is_dir():
                raise EmbeddingModelUnavailable(f"EMBEDDING_MODEL_PATH 不存在：{resolved}")
            return str(resolved)
        return self._settings.embedding_model_name

    @property
    def metadata(self) -> EmbeddingMetadata:
        """Return (and lazily compute) the model audit metadata."""
        self._ensure_model()
        assert self._metadata is not None
        return self._metadata

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            try:
                from FlagEmbedding import BGEM3FlagModel
            except ImportError as exc:  # pragma: no cover - dependency guard
                raise EmbeddingModelUnavailable("未安装 FlagEmbedding，无法加载 BGE-M3") from exc

            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            reference = self.model_reference
            is_local = Path(reference).is_dir()
            kwargs: dict[str, Any] = {
                "use_fp16": False,
                "devices": self._settings.embedding_device or "cpu",
                "normalize_embeddings": True,
            }
            cache_dir = self._settings.embedding_cache_dir.strip()
            if cache_dir:
                kwargs["cache_dir"] = cache_dir
            if is_local:
                kwargs["local_files_only"] = True
            elif self._settings.embedding_model_revision.strip():
                kwargs["revision"] = self._settings.embedding_model_revision.strip()
            try:
                model = BGEM3FlagModel(reference, **kwargs)
            except Exception as exc:
                raise EmbeddingModelUnavailable(f"BGE-M3 权重加载失败：{reference}") from exc

            revision = (
                str(getattr(getattr(model.model, "config", None), "_commit_hash", "") or "")
                or self._settings.embedding_model_revision.strip()
                or ("local" if is_local else "")
            )
            self._metadata = EmbeddingMetadata(
                model=self._settings.embedding_model_name,
                provider=self.name,
                dimension=self.dimension,
                revision=revision or "unknown",
                fingerprint=_weight_fingerprint(model),
            )
            self._model = model
            return model

    def warmup(self) -> EmbeddingMetadata:
        """Load the weights eagerly and return their metadata (used by verify scripts)."""
        return self.metadata

    # -- encoding ----------------------------------------------------------
    def _encode(self, texts: Sequence[str]) -> list[HybridVector]:
        if not texts:
            return []
        model = self._ensure_model()
        payload = [text if text.strip() else " " for text in texts]
        with self._encode_lock:
            output = model.encode(
                payload,
                batch_size=self._settings.embedding_batch_size,
                max_length=self._settings.embedding_max_length,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
            )
        dense_vectors = output["dense_vecs"]
        sparse_weights = output["lexical_weights"]
        if len(dense_vectors) != len(texts) or len(sparse_weights) != len(texts):
            raise InvalidEmbeddingError(
                "EMBEDDING_OUTPUT_LENGTH", "模型返回的向量数量与输入文本数量不一致"
            )
        results: list[HybridVector] = []
        for index, raw_dense in enumerate(dense_vectors):
            dense = l2_normalise([float(value) for value in raw_dense], dimension=self.dimension)
            sparse = to_sparse_weights(sparse_weights[index])
            if not sparse:
                raise InvalidEmbeddingError(
                    "EMBEDDING_EMPTY_SPARSE", "BGE-M3 未产出 sparse 权重，拒绝生成可检索向量"
                )
            results.append(HybridVector(dense=dense, sparse=sparse))
        return results

    def embed_documents_hybrid(self, texts: Sequence[str]) -> list[HybridVector]:
        """Embed chunk texts; order and length always match the input."""
        return self._encode(texts)

    def embed_query_hybrid(self, text: str) -> HybridVector:
        """Embed one query with the same model, normalisation and sparse logic."""
        if not text.strip():
            raise InvalidEmbeddingError("EMBEDDING_EMPTY_QUERY", "查询文本为空")
        return self._encode([text])[0]

    # -- dense-only helpers (fixtures, ablation fallbacks) ------------------
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Return only dense vectors (callers that need sparse must use the hybrid API)."""
        return [list(vector.dense) for vector in self._encode(texts)]

    def embed_query(self, text: str) -> list[float]:
        """Return only the dense query vector."""
        return list(self.embed_query_hybrid(text).dense)


_singleton: BgeM3EmbeddingProvider | None = None
_singleton_lock = threading.Lock()


def get_bge_m3_provider(settings: Settings | None = None) -> BgeM3EmbeddingProvider:
    """Return the process-wide BGE-M3 provider (loading is still lazy).

    A single instance keeps one copy of the ~2GB weights in memory. Uvicorn must run with
    one worker, or the model should move to a dedicated service.
    """
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                from shopmate_ecommerce_assistant.core.config import get_settings

                _singleton = BgeM3EmbeddingProvider(settings or get_settings())
    return _singleton


def reset_bge_m3_provider() -> None:
    """Drop the cached singleton (tests only)."""
    global _singleton
    with _singleton_lock:
        _singleton = None


def build_embedding_provider(settings: Settings) -> BgeM3EmbeddingProvider:
    """Return the production embedding provider.

    Only BGE-M3 is wired here on purpose: there is no config switch that could silently
    substitute a weaker encoder in the retrieval path.
    """
    return get_bge_m3_provider(settings)
