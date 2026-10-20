"""Rate limiter tests: fixed-window counting for the in-memory and Redis backends."""

from __future__ import annotations

import time
from typing import Any

from shopmate_ecommerce_assistant.core.rate_limit import InMemoryRateLimiter, RedisRateLimiter


class _FakePipeline:
    def __init__(self, store: dict[str, int]) -> None:
        self._store = store
        self._last_key: str | None = None
        self._results: list[Any] = []

    def incr(self, key: str) -> _FakePipeline:
        self._last_key = key
        self._store[key] = self._store.get(key, 0) + 1
        self._results.append(self._store[key])
        return self

    def expire(self, key: str, seconds: int) -> _FakePipeline:
        self._results.append(None)
        return self

    def ttl(self, key: str) -> _FakePipeline:
        self._results.append(300)
        return self

    async def execute(self) -> list[Any]:
        return self._results


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self.store)


async def test_in_memory_allows_up_to_limit_then_blocks() -> None:
    limiter = InMemoryRateLimiter()

    results = [await limiter.check("k", limit=3, window_seconds=60) for _ in range(3)]
    assert all(allowed for allowed, _ in results)

    allowed, retry_after = await limiter.check("k", limit=3, window_seconds=60)
    assert allowed is False
    assert retry_after > 0


async def test_in_memory_window_resets_after_expiry() -> None:
    limiter = InMemoryRateLimiter()
    assert (await limiter.check("k", limit=1, window_seconds=60))[0] is True
    assert (await limiter.check("k", limit=1, window_seconds=60))[0] is False

    # Force the window open by backdating the stored window start.
    now = time.monotonic()
    limiter._counts["k"] = (1, now - 61)
    assert (await limiter.check("k", limit=1, window_seconds=60))[0] is True


async def test_redis_limiter_blocks_after_limit() -> None:
    redis = _FakeRedis()
    limiter = RedisRateLimiter(redis)

    for _ in range(2):
        allowed, _ = await limiter.check("chat:u1", limit=2, window_seconds=60)
        assert allowed is True

    allowed, retry_after = await limiter.check("chat:u1", limit=2, window_seconds=60)
    assert allowed is False
    assert retry_after > 0
    assert redis.store["chat:u1"] == 3


async def test_redis_limiter_uses_separate_keys() -> None:
    redis = _FakeRedis()
    limiter = RedisRateLimiter(redis)

    await limiter.check("chat:u1", limit=1, window_seconds=60)
    allowed, _ = await limiter.check("chat:u2", limit=1, window_seconds=60)
    assert allowed is True
