"""FAQ high-confidence matching and versioned Redis cache.

Two separate mechanisms, deliberately not merged:

1. :class:`FaqIndex` matches a question against ``data/knowledge/faq.jsonl`` at high
   confidence. The match is a *retrieval hint and canonical question*, not an answer
   source: an FAQ row has no chunk id, page or effective window, so serving its "answer"
   directly would violate the "policy answers must carry citations" rule.
2. :class:`FaqAnswerCache` stores **already grounded** policy answers (answer text plus
   citation labels) in Redis. Only low-risk, evidence-sufficient, cited ``policy_faq``
   answers may be stored. The key contains shop, region, locale, knowledge base and the
   current knowledge version, so publishing a new document version simply produces a new
   key; stale payloads are also rejected and deleted on read.

Real-time facts (price, stock, order, shipment) are never stored here: the intent gate and
:func:`shopmate_ecommerce_assistant.safety.risk` both have to say "low risk policy" first.
"""

from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from redis.asyncio import Redis

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.paths import FAQ_PATH
from shopmate_ecommerce_assistant.safety.output_guard import OutputGuardResult, guard_output

logger = logging.getLogger(__name__)

FAQ_CACHEABLE_INTENT = "policy_faq"
FAQ_CACHEABLE_RISK = "low"
FAQ_MAX_QUESTION_CHARS = 200


# -- normalisation and matching -------------------------------------------


_FILLERS: tuple[str, ...] = (
    "请问一下",
    "请问",
    "你好",
    "您好",
    "麻烦你",
    "麻烦",
    "想问一下",
    "我想问一下",
    "我想问",
    "我想知道",
    "帮我看看",
    "谢谢",
    "那个",
)


def normalize_question(text: str) -> str:
    """Normalise a question so formatting differences cannot miss the cache."""
    value = unicodedata.normalize("NFKC", text or "").lower().strip()
    for filler in _FILLERS:
        value = value.replace(filler, "")
    kept = [
        char
        for char in value
        if not char.isspace() and not unicodedata.category(char).startswith(("P", "Z"))
    ]
    return "".join(kept)[:FAQ_MAX_QUESTION_CHARS]


def _bigrams(text: str) -> frozenset[str]:
    if len(text) < 2:
        return frozenset({text}) if text else frozenset()
    return frozenset(text[index : index + 2] for index in range(len(text) - 1))


@dataclass(frozen=True, slots=True)
class FaqRecord:
    """One curated FAQ entry, bound to the policy document that justifies it."""

    faq_id: str
    question: str
    answer: str
    category: str
    region: str
    locale: str
    policy_document_key: str
    tags: tuple[str, ...] = ()
    is_synthetic: bool = True

    @property
    def normalized(self) -> str:
        """Return the normalised question used for lookup."""
        return normalize_question(self.question)


@dataclass(frozen=True, slots=True)
class FaqMatch:
    """The best FAQ candidate and why it was (not) accepted."""

    record: FaqRecord | None
    confidence: float
    reason: str
    normalized_question: str

    @property
    def matched(self) -> bool:
        """Return True when the match cleared the confidence threshold."""
        return self.record is not None

    def as_dict(self) -> dict[str, Any]:
        """Return an audit-safe representation (no answer text)."""
        return {
            "matched": self.matched,
            "faq_id": self.record.faq_id if self.record else None,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
        }


class FaqIndex:
    """In-memory, region/locale-scoped FAQ matcher."""

    def __init__(self, records: Iterable[FaqRecord], *, skipped: int = 0) -> None:
        self._records = tuple(records)
        self.skipped = skipped
        self._by_normalized: dict[str, list[FaqRecord]] = {}
        for record in self._records:
            self._by_normalized.setdefault(record.normalized, []).append(record)

    @property
    def records(self) -> tuple[FaqRecord, ...]:
        """Return every loaded record."""
        return self._records

    def __len__(self) -> int:
        return len(self._records)

    def _in_scope(self, record: FaqRecord, region: str | None, locale: str | None) -> bool:
        if region and record.region and record.region != region:
            return False
        if locale and record.locale and record.locale != locale:
            return False
        return True

    def match(
        self,
        question: str,
        *,
        region: str | None = None,
        locale: str | None = None,
        min_confidence: float = 0.86,
    ) -> FaqMatch:
        """Return the best in-scope FAQ match at or above ``min_confidence``."""
        normalized = normalize_question(question)
        if not normalized:
            return FaqMatch(None, 0.0, "empty", normalized)

        exact = self._by_normalized.get(normalized, [])
        in_scope = [record for record in exact if self._in_scope(record, region, locale)]
        if in_scope:
            return FaqMatch(in_scope[0], 1.0, "exact", normalized)
        if exact:
            return FaqMatch(None, 0.0, "region_mismatch", normalized)

        target = _bigrams(normalized)
        if not target:
            return FaqMatch(None, 0.0, "empty", normalized)

        best: FaqRecord | None = None
        best_score = 0.0
        for record in self._records:
            if not self._in_scope(record, region, locale):
                continue
            candidate = _bigrams(record.normalized)
            if not candidate:
                continue
            score = 2 * len(target & candidate) / (len(target) + len(candidate))
            if score > best_score or (
                score == best_score and best is not None and record.faq_id < best.faq_id
            ):
                best, best_score = record, score

        if best is not None and best_score >= min_confidence:
            return FaqMatch(best, best_score, "fuzzy", normalized)
        reason = "below_threshold" if best is not None else "no_candidate"
        return FaqMatch(None, best_score, reason, normalized)


def load_faq_index(path: Path | str | None = None) -> FaqIndex:
    """Load ``faq.jsonl``; malformed rows are skipped and counted, never guessed."""
    resolved = Path(path) if path is not None else FAQ_PATH
    if not resolved.is_file():
        logger.warning("FAQ file not found: %s", resolved.name)
        return FaqIndex((), skipped=0)
    records: list[FaqRecord] = []
    skipped = 0
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                records.append(
                    FaqRecord(
                        faq_id=str(payload["id"]),
                        question=str(payload["question"]),
                        answer=str(payload["answer"]),
                        category=str(payload.get("category", "")),
                        region=str(payload.get("region", "")),
                        locale=str(payload.get("locale", "")),
                        policy_document_key=str(payload.get("policy_document_key", "")),
                        tags=tuple(str(tag) for tag in payload.get("tags", []) or []),
                        is_synthetic=bool(payload.get("is_synthetic", True)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                skipped += 1
    if skipped:
        logger.warning("FAQ rows skipped: %d", skipped)
    return FaqIndex(records, skipped=skipped)


# -- cache ----------------------------------------------------------------


class CacheBackend(Protocol):
    """Minimal async KV contract; Redis in production, a fake in tests."""

    async def get(self, key: str) -> str | None:
        """Return the stored value or ``None``."""

    async def set(self, key: str, value: str, *, ex: int) -> None:
        """Store ``value`` with a TTL in seconds."""

    async def delete(self, key: str) -> None:
        """Delete one key (missing keys are ignored)."""

    async def keys(self, pattern: str) -> list[str]:
        """Return keys matching a prefix pattern (bounded by the caller)."""


class RedisCacheBackend:
    """Redis implementation; ``decode_responses=True`` is assumed."""

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def get(self, key: str) -> str | None:
        value = await self._client.get(key)
        if value is None:
            return None
        return value if isinstance(value, str) else value.decode("utf-8")

    async def set(self, key: str, value: str, *, ex: int) -> None:
        await self._client.set(key, value, ex=ex)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def keys(self, pattern: str) -> list[str]:
        found: list[str] = []
        async for key in self._client.scan_iter(match=pattern, count=200):
            found.append(key if isinstance(key, str) else key.decode("utf-8"))
        return found


@dataclass(frozen=True, slots=True)
class FaqCacheScope:
    """Dimensions that make one cached answer safe to reuse."""

    shop_id: str
    region: str
    locale: str
    knowledge_version: str
    knowledge_base_id: str | None = None


@dataclass(frozen=True, slots=True)
class CachedFaqAnswer:
    """A grounded policy answer stored in Redis."""

    question: str
    answer: str
    citation_labels: tuple[str, ...]
    citations: tuple[dict[str, Any], ...]
    knowledge_version: str
    intent: str
    created_at: str
    faq_id: str | None = None
    faq_question: str | None = None

    def to_payload(self) -> str:
        """Serialise for Redis."""
        return json.dumps(
            {
                "question": self.question,
                "answer": self.answer,
                "citation_labels": list(self.citation_labels),
                "citations": list(self.citations),
                "knowledge_version": self.knowledge_version,
                "intent": self.intent,
                "created_at": self.created_at,
                "faq_id": self.faq_id,
                "faq_question": self.faq_question,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_payload(cls, raw: str) -> CachedFaqAnswer:
        """Parse a stored payload, raising ``ValueError`` on corruption."""
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("cached FAQ payload is not an object")
        citations = payload.get("citations") or []
        labels = payload.get("citation_labels") or []
        return cls(
            question=str(payload["question"]),
            answer=str(payload["answer"]),
            citation_labels=tuple(str(label) for label in labels),
            citations=tuple(dict(item) for item in citations),
            knowledge_version=str(payload["knowledge_version"]),
            intent=str(payload["intent"]),
            created_at=str(payload["created_at"]),
            faq_id=payload.get("faq_id"),
            faq_question=payload.get("faq_question"),
        )


@dataclass(frozen=True, slots=True)
class CacheLookup:
    """Result of one cache read."""

    hit: bool
    key: str
    reason: str
    answer: CachedFaqAnswer | None = None

    @property
    def citations(self) -> tuple[dict[str, Any], ...]:
        """Return the cached citations for display."""
        return self.answer.citations if self.answer else ()


@dataclass(frozen=True, slots=True)
class CacheWrite:
    """Result of one cache write attempt."""

    stored: bool
    key: str
    reason: str


class FaqAnswerCache:
    """Version-keyed cache for grounded policy answers."""

    def __init__(
        self,
        backend: CacheBackend,
        *,
        settings: Settings | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._backend = backend
        self._settings = settings or Settings(_env_file=None)  # type: ignore[call-arg]
        self._clock = clock or (lambda: datetime.now(UTC))

    def build_key(self, question: str, scope: FaqCacheScope) -> str:
        """Build a key containing shop, region, locale, KB, knowledge version and question."""
        digest = hashlib.sha256(
            f"{normalize_question(question)}|{scope.knowledge_version}".encode()
        ).hexdigest()[:16]
        return ":".join(
            (
                self._settings.faq_cache_key_prefix,
                scope.shop_id,
                scope.region,
                scope.locale,
                scope.knowledge_base_id or "-",
                scope.knowledge_version,
                digest,
            )
        )

    async def get(self, question: str, scope: FaqCacheScope) -> CacheLookup:
        """Read and re-validate a cached answer; cache failures are misses, never errors."""
        key = self.build_key(question, scope)
        if not self._settings.faq_cache_enabled:
            return CacheLookup(False, key, "disabled")
        try:
            raw = await self._backend.get(key)
        except Exception:
            logger.warning("FAQ cache read failed; falling back to retrieval")
            return CacheLookup(False, key, "unavailable")
        if raw is None:
            return CacheLookup(False, key, "not_found")
        try:
            answer = CachedFaqAnswer.from_payload(raw)
        except (ValueError, KeyError, TypeError):
            await self.delete_key(key)
            return CacheLookup(False, key, "corrupt")
        if answer.knowledge_version != scope.knowledge_version:
            await self.delete_key(key)
            return CacheLookup(False, key, "stale_version")
        return CacheLookup(True, key, "hit", answer)

    async def put(
        self,
        question: str,
        scope: FaqCacheScope,
        answer: CachedFaqAnswer,
        *,
        intent: str,
        risk_level: str,
        evidence_sufficient: bool,
        injection_detected: bool = False,
    ) -> CacheWrite:
        """Store an answer only when every cacheability rule is satisfied."""
        key = self.build_key(question, scope)
        reason = self._write_rejection(
            scope=scope,
            answer=answer,
            intent=intent,
            risk_level=risk_level,
            evidence_sufficient=evidence_sufficient,
            injection_detected=injection_detected,
        )
        if reason:
            return CacheWrite(False, key, reason)
        if not self._settings.faq_cache_enabled:
            return CacheWrite(False, key, "disabled")
        try:
            await self._backend.set(
                key, answer.to_payload(), ex=self._settings.faq_cache_ttl_seconds
            )
        except Exception:
            logger.warning("FAQ cache write failed; answer still served")
            return CacheWrite(False, key, "unavailable")
        return CacheWrite(True, key, "stored")

    def _write_rejection(
        self,
        *,
        scope: FaqCacheScope,
        answer: CachedFaqAnswer,
        intent: str,
        risk_level: str,
        evidence_sufficient: bool,
        injection_detected: bool,
    ) -> str | None:
        if intent != FAQ_CACHEABLE_INTENT:
            return "intent_not_cacheable"
        if risk_level != FAQ_CACHEABLE_RISK:
            return "risk_not_cacheable"
        if not evidence_sufficient:
            return "no_evidence"
        if injection_detected:
            return "injection_flagged"
        if not answer.citation_labels or not answer.citations:
            return "no_citations"
        if answer.knowledge_version != scope.knowledge_version:
            return "version_mismatch"
        return None

    async def invalidate_shop(self, shop_id: str, *, limit: int = 1000) -> int:
        """Delete every cached answer for a shop (call after publishing knowledge)."""
        pattern = f"{self._settings.faq_cache_key_prefix}:{shop_id}:*"
        try:
            keys = (await self._backend.keys(pattern))[:limit]
            for key in keys:
                await self._backend.delete(key)
        except Exception:
            logger.warning("FAQ cache invalidation failed")
            return 0
        return len(keys)

    async def delete_key(self, key: str) -> None:
        """Delete one key, swallowing backend errors (invalidation is best-effort)."""
        try:
            await self._backend.delete(key)
        except Exception:
            logger.warning("FAQ cache delete failed")


# -- service --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FaqLookup:
    """FAQ match plus cache decision for one policy question."""

    match: FaqMatch
    effective_question: str
    cache: CacheLookup
    guard: OutputGuardResult | None = None

    @property
    def answer(self) -> CachedFaqAnswer | None:
        """Return the cached answer only when the cache hit survived the guard."""
        return self.cache.answer if self.cache.hit else None

    @property
    def citations(self) -> tuple[dict[str, Any], ...]:
        """Return citations to display with a cache hit."""
        return self.cache.citations if self.cache.hit else ()

    def as_dict(self) -> dict[str, Any]:
        """Return an audit/SSE-safe representation."""
        return {
            "faq": self.match.as_dict(),
            "cache": {
                "hit": self.cache.hit,
                "reason": self.cache.reason,
                "key_digest": self.cache.key.rsplit(":", 1)[-1],
                "citations": len(self.citations),
            },
            "guard": self.guard.as_dict() if self.guard else None,
        }


class FaqService:
    """FAQ match + cache facade used by the chat path."""

    def __init__(
        self,
        index: FaqIndex,
        cache: FaqAnswerCache,
        *,
        settings: Settings | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._index = index
        self._cache = cache
        self._settings = settings or Settings(_env_file=None)  # type: ignore[call-arg]
        self._clock = clock or (lambda: datetime.now(UTC))

    def match(self, question: str, *, scope: FaqCacheScope) -> FaqMatch:
        """Match against the FAQ index within the request's region and locale."""
        return self._index.match(
            question,
            region=scope.region,
            locale=scope.locale,
            min_confidence=self._settings.faq_min_match_confidence,
        )

    async def lookup(self, question: str, *, scope: FaqCacheScope) -> FaqLookup:
        """Return a guarded cached answer, or a miss that must go through RAG."""
        match = self.match(question, scope=scope)
        effective = match.record.question if match.record else question
        lookup = await self._cache.get(effective, scope)
        if not lookup.hit or lookup.answer is None:
            return FaqLookup(match=match, effective_question=effective, cache=lookup)

        guard = guard_output(
            lookup.answer.answer,
            intent=FAQ_CACHEABLE_INTENT,
            citation_labels=lookup.answer.citation_labels,
        )
        if not guard.allowed or guard.handoff_required:
            await self._cache.delete_key(lookup.key)
            return FaqLookup(
                match=match,
                effective_question=effective,
                cache=CacheLookup(False, lookup.key, "guard_rejected"),
                guard=guard,
            )
        return FaqLookup(match=match, effective_question=effective, cache=lookup, guard=guard)

    async def remember(
        self,
        question: str,
        *,
        scope: FaqCacheScope,
        answer: str,
        citations: Sequence[dict[str, Any]],
        intent: str,
        risk_level: str,
        evidence_sufficient: bool,
        route_cache_eligible: bool,
        injection_detected: bool = False,
    ) -> CacheWrite:
        """Store a grounded answer; the FAQ match canonicalises the cache key.

        Every cacheability input is a **required** keyword argument on purpose: a default
        of ``intent="policy_faq"``/``risk_level="low"``/``evidence_sufficient=True`` turns a
        forgotten argument into a silently cached answer, i.e. a fail-open cache. Callers
        must pass the router's own decision (``route.cache_eligible``) as
        ``route_cache_eligible``; ``False`` rejects the write before anything is stored.
        """
        match = self.match(question, scope=scope)
        effective = match.record.question if match.record else question
        if not route_cache_eligible:
            return CacheWrite(False, self._cache.build_key(effective, scope), "route_not_cacheable")
        labels = tuple(
            str(citation.get("label")) for citation in citations if citation.get("label")
        )
        payload = CachedFaqAnswer(
            question=effective,
            answer=answer,
            citation_labels=labels,
            citations=tuple(citations),
            knowledge_version=scope.knowledge_version,
            intent=intent,
            created_at=self._clock().isoformat(),
            faq_id=match.record.faq_id if match.record else None,
            faq_question=match.record.question if match.record else None,
        )
        return await self._cache.put(
            effective,
            scope,
            payload,
            intent=intent,
            risk_level=risk_level,
            evidence_sufficient=evidence_sufficient,
            injection_detected=injection_detected,
        )


def build_faq_service(redis: Redis, settings: Settings | None = None) -> FaqService:
    """Build the production FAQ service around an existing Redis client."""
    resolved = settings or Settings(_env_file=None)  # type: ignore[call-arg]
    return FaqService(
        load_faq_index(),
        FaqAnswerCache(RedisCacheBackend(redis), settings=resolved),
        settings=resolved,
    )


__all__ = [
    "CacheBackend",
    "CacheLookup",
    "CacheWrite",
    "CachedFaqAnswer",
    "FaqAnswerCache",
    "FaqCacheScope",
    "FaqIndex",
    "FaqLookup",
    "FaqMatch",
    "FaqRecord",
    "FaqService",
    "RedisCacheBackend",
    "build_faq_service",
    "load_faq_index",
    "normalize_question",
]
