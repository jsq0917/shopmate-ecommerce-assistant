"""Redis-backed fixed-window rate limiting (stage 10).

The limiter returns ``(allowed, retry_after_seconds)`` for a scoped key. A key is a
server-assembled string such as ``auth:login:<ip>`` or ``chat:<user_id>`` — never raw user
input — so the limiter cannot be used to enumerate accounts or store PII.

The production implementation uses ``INCR`` + ``EXPIRE`` atomically; an ``InMemoryLimiter``
provides a deterministic, no-network stand-in for unit tests and single-process dev.
"""

from __future__ import annotations

import time
from typing import Any, Protocol


class RateLimiter(Protocol):
    """Count one request for a key and decide whether it is allowed."""

    async def check(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, float]:
        """Return ``(allowed, retry_after_seconds)`` after recording this attempt."""


class RedisRateLimiter:
    """Fixed-window limiter backed by Redis."""

    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def check(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, float]:
        """Record and gate one request in a fixed window."""
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        pipe.ttl(key)
        count, _, ttl = await pipe.execute()

        if int(count) <= limit:
            return True, 0.0
        return False, float(max(ttl, 0) if ttl is not None and ttl > 0 else window_seconds)


class InMemoryRateLimiter:
    """Deterministic, single-process limiter for tests and dev without Redis."""

    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, float]] = {}

    async def check(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, float]:
        """Record and gate one request against an in-memory window."""
        now = time.monotonic()
        count, window_start = self._counts.get(key, (0, now))
        if now - window_start >= window_seconds:
            count, window_start = 0, now
        count += 1
        self._counts[key] = (count, window_start)
        if count <= limit:
            return True, 0.0
        return False, max(0.0, window_seconds - (now - window_start))


__all__ = ["InMemoryRateLimiter", "RateLimiter", "RedisRateLimiter"]
