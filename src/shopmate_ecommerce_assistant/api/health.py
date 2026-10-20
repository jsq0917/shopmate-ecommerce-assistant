"""Liveness and readiness endpoints."""

import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Literal, Protocol

import httpx
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness response."""

    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    """Readiness response with dependency-level outcomes."""

    status: Literal["ready", "not_ready"]
    checks: dict[str, str]
    as_of: datetime


class ReadinessChecker(Protocol):
    """Protocol used by the readiness route and tests."""

    async def check(self) -> dict[str, str]:
        """Return dependency name to safe status mappings."""


class InfrastructureReadinessChecker:
    """Check the infrastructure required by the API."""

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        redis: Redis,
        http_client: httpx.AsyncClient,
        milvus_health_url: str,
        timeout_seconds: float,
    ) -> None:
        self._engine = engine
        self._redis = redis
        self._http_client = http_client
        self._milvus_health_url = milvus_health_url
        self._timeout_seconds = timeout_seconds

    async def check(self) -> dict[str, str]:
        """Check PostgreSQL, Redis, and Milvus without exposing exception details."""
        checks = await asyncio.gather(
            self._safe_check("postgres", self._check_postgres()),
            self._safe_check("redis", self._check_redis()),
            self._safe_check("milvus", self._check_milvus()),
        )
        return dict(checks)

    async def _safe_check(
        self,
        name: str,
        operation: Awaitable[None],
    ) -> tuple[str, str]:
        try:
            await asyncio.wait_for(operation, timeout=self._timeout_seconds)
        except Exception:
            return name, "error"
        return name, "ok"

    async def _check_postgres(self) -> None:
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def _check_redis(self) -> None:
        result = await self._redis.ping()
        if not result:
            raise RuntimeError("Redis ping returned false")

    async def _check_milvus(self) -> None:
        response = await self._http_client.get(self._milvus_health_url)
        response.raise_for_status()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report process liveness without checking external dependencies."""
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
async def ready(request: Request, response: Response) -> ReadyResponse:
    """Report whether all API dependencies are available."""
    checker: ReadinessChecker = request.app.state.readiness_checker
    try:
        checks = await checker.check()
    except Exception:
        checks = {"readiness": "error"}

    is_ready = bool(checks) and all(result == "ok" for result in checks.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadyResponse(
        status="ready" if is_ready else "not_ready",
        checks=checks,
        as_of=datetime.now(UTC),
    )
