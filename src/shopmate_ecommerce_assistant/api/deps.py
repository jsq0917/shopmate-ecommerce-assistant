"""FastAPI dependencies: sessions, authentication, authorization and rate limiting.

Identity always comes from the verified bearer token, never from a request body. Tenant
scope (``shop_id``) and role are part of that token, so a request cannot widen them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.core.config import Settings, get_settings
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.rate_limit import InMemoryRateLimiter, RateLimiter
from shopmate_ecommerce_assistant.core.security import (
    AccessContext,
    AuthError,
    decode_access_token,
)
from shopmate_ecommerce_assistant.db.models.enums import UserRole
from shopmate_ecommerce_assistant.tools.context import ConfirmationGrant, RiskContext, ToolContext

_bearer = HTTPBearer(auto_error=False)

RATE_LIMITED_MESSAGE = "请求过于频繁，请稍后重试。"


def get_settings_dep() -> Settings:
    """Return the process-wide settings instance."""
    return get_settings()


async def get_session(request: Request) -> AsyncSession:
    """Yield a database session bound to the application engine."""
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def _access_context(
    request: Request, credentials: HTTPAuthorizationCredentials | None
) -> AccessContext:
    if credentials is None or not credentials.scheme or credentials.scheme.lower() != "bearer":
        raise AuthError("UNAUTHENTICATED", "请先登录后再访问。")
    settings: Settings = request.app.state.settings
    return decode_access_token(settings, credentials.credentials)


async def get_access_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AccessContext:
    """Return the verified identity context from the bearer token."""
    return _access_context(request, credentials)


def require_role(*roles: UserRole) -> Callable[..., AccessContext]:
    """Return a dependency that enforces one of ``roles``."""

    async def _dep(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> AccessContext:
        context = _access_context(request, credentials)
        if context.role not in roles:
            raise AuthError("FORBIDDEN", "当前账号没有执行该操作的权限。")
        return context

    return _dep


def require_permission(permission: str) -> Callable[..., AccessContext]:
    """Return a dependency that enforces a named permission."""

    async def _dep(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> AccessContext:
        context = _access_context(request, credentials)
        if not context.has_permission(permission):
            raise AuthError("FORBIDDEN", "当前账号没有执行该操作的权限。")
        return context

    return _dep


def get_rate_limiter(request: Request) -> RateLimiter:
    """Return the application-wide rate limiter."""
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return InMemoryRateLimiter()
    return limiter


def rate_limit(key_builder: Callable[[Request, AccessContext], str], *, limit: int, window: int):
    """Return a dependency that gates a request by a server-assembled key."""

    async def _dep(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
        limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    ) -> AccessContext:
        # Auth endpoints may be unauthenticated; use the IP when there is no token.
        if credentials is not None and credentials.scheme.lower() == "bearer":
            try:
                context = _access_context(request, credentials)
            except AuthError:
                context = None
        else:
            context = None
        key = key_builder(request, context)
        allowed, retry_after = await limiter.check(key, limit=limit, window_seconds=window)
        if not allowed:
            raise ToolError(
                ErrorCode.RATE_LIMITED,
                RATE_LIMITED_MESSAGE,
                retryable=True,
                retry_after_ms=int(retry_after * 1000),
            )
        if context is not None:
            return context
        raise AuthError("UNAUTHENTICATED", "请先登录后再访问。")

    return _dep


def client_ip(request: Request) -> str:
    """Return a stable, non-PII client identifier for rate limiting."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_request_ids(request: Request) -> tuple[UUID, UUID]:
    """Return the correlation ids attached by the middleware (or safe fallbacks)."""
    request_id = getattr(request.state, "request_id", None)
    trace_id = getattr(request.state, "trace_id", None)
    if not isinstance(request_id, UUID):
        request_id = uuid4()
    if not isinstance(trace_id, UUID):
        trace_id = uuid4()
    return request_id, trace_id


def build_tool_context(
    ctx: AccessContext,
    *,
    request_id: UUID,
    trace_id: UUID,
    conversation_id: UUID | None = None,
    risk_context: RiskContext | None = None,
    idempotency_key: str | None = None,
    route_confidence: float | None = None,
    confirmation: ConfirmationGrant | None = None,
    clarification_attempted: bool = False,
) -> ToolContext:
    """Build a server-owned tool context from a verified access context."""
    return ToolContext(
        shop_id=ctx.shop_id,
        actor_user_id=ctx.user_id,
        role=ctx.role,
        request_id=request_id,
        trace_id=trace_id,
        permissions=ctx.permissions,
        conversation_id=conversation_id,
        risk_context=risk_context,
        idempotency_key=idempotency_key,
        route_confidence=route_confidence,
        confirmation=confirmation,
        clarification_attempted=clarification_attempted,
    )


__all__ = [
    "build_tool_context",
    "client_ip",
    "get_access_context",
    "get_rate_limiter",
    "get_request_ids",
    "get_session",
    "get_settings_dep",
    "rate_limit",
    "require_permission",
    "require_role",
]
