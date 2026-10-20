"""Unified error mapping and exception handlers (docs/06-api.md section 3.3 and 14).

Every failure is rendered as ``{error: {...}, request_id, trace_id}`` with a stable
``code``, a Chinese ``message``, ``retryable`` and ``retry_after_ms``. No SQL, stack trace,
connection string, token or PII ever reaches the client; the server may log the reason
separately, but the response only carries the contract fields.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from shopmate_ecommerce_assistant.core.errors import ToolError
from shopmate_ecommerce_assistant.core.security import AuthError
from shopmate_ecommerce_assistant.db.repositories.conversations import MessageConflictError

logger = logging.getLogger(__name__)

#: Tool error code -> HTTP status. Business "not found" and "conflict" outcomes are mapped
#: to the statuses fixed by docs/06-api.md section 14.
_TOOL_STATUS: dict[str, int] = {
    "VALIDATION_ERROR": 400,
    "FORBIDDEN": 403,
    "PRODUCT_NOT_FOUND": 404,
    "VARIANT_NOT_FOUND": 404,
    "ORDER_NOT_FOUND": 404,
    "SHIPMENT_NOT_FOUND": 404,
    "CONVERSATION_NOT_FOUND": 404,
    "OUT_OF_STOCK": 409,
    "INVALID_STATE": 409,
    "RETURN_NOT_ALLOWED": 409,
    "RETURN_WINDOW_EXPIRED": 409,
    "DUPLICATE_RETURN": 409,
    "MANUAL_REVIEW_REQUIRED": 409,
    "LOW_CONFIDENCE": 409,
    "CONFIRMATION_REQUIRED": 409,
    "ELIGIBILITY_EXPIRED": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "IDEMPOTENCY_IN_PROGRESS": 409,
    "RISK_HANDOFF_REQUIRED": 409,
    "TOOL_BUDGET_EXCEEDED": 429,
    "UPSTREAM_UNAVAILABLE": 503,
    "RATE_LIMITED": 429,
    "INTERNAL_ERROR": 500,
}

#: Auth error code -> HTTP status.
_AUTH_STATUS: dict[str, int] = {
    "UNAUTHENTICATED": 401,
    "CSRF_INVALID": 403,
    "FORBIDDEN": 403,
}

#: Protocol-level error codes carried as HTTP status when an unhandled exception escapes.
_INTERNAL_MESSAGE = "服务暂时不可用，请稍后重试。"
_VALIDATION_MESSAGE = "请求参数不合法，请检查后重试。"


def _request_ids(request: Request) -> tuple[UUID, UUID]:
    """Return the request ids attached by the middleware, or safe fallbacks."""
    request_id = getattr(request.state, "request_id", None)
    trace_id = getattr(request.state, "trace_id", None)
    if not isinstance(request_id, UUID) or not isinstance(trace_id, UUID):
        from uuid import uuid4

        return uuid4(), uuid4()
    return request_id, trace_id


def error_response(
    request: Request,
    *,
    code: str,
    message: str,
    http_status: int,
    retryable: bool = False,
    retry_after_ms: int | None = None,
    details: dict | None = None,
) -> JSONResponse:
    """Build the standard error envelope."""
    request_id, trace_id = _request_ids(request)
    return JSONResponse(
        status_code=http_status,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "retry_after_ms": retry_after_ms,
                "details": details or {},
            },
            "request_id": str(request_id),
            "trace_id": str(trace_id),
        },
    )


def tool_error_response(request: Request, exc: ToolError) -> JSONResponse:
    """Map a controlled tool failure to its HTTP envelope."""
    code = exc.code.value
    http_status = _TOOL_STATUS.get(code, 400)
    return error_response(
        request,
        code=code,
        message=exc.user_message,
        http_status=http_status,
        retryable=exc.retryable,
        retry_after_ms=exc.retry_after_ms,
    )


def auth_error_response(request: Request, exc: AuthError) -> JSONResponse:
    """Map an authentication/authorization failure to its HTTP envelope."""
    http_status = _AUTH_STATUS.get(exc.code, 401)
    return error_response(
        request,
        code=exc.code,
        message=exc.message,
        http_status=http_status,
        retryable=False,
    )


def install_exception_handlers(app: FastAPI) -> None:
    """Register handlers that render every failure in the unified envelope."""

    @app.exception_handler(ToolError)
    async def _tool(request: Request, exc: ToolError) -> JSONResponse:
        return tool_error_response(request, exc)

    @app.exception_handler(AuthError)
    async def _auth(request: Request, exc: AuthError) -> JSONResponse:
        return auth_error_response(request, exc)

    @app.exception_handler(MessageConflictError)
    async def _message_conflict(request: Request, exc: MessageConflictError) -> JSONResponse:
        return error_response(
            request,
            code="DUPLICATE_REQUEST",
            message="这条消息已经提交过，请读取历史记录，不要重复发送。",
            http_status=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            request,
            code="VALIDATION_ERROR",
            message=_VALIDATION_MESSAGE,
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Deliberately no exc_info in the response: an unexpected error may echo user input.
        logger.error("unhandled API error: %s", type(exc).__name__)
        return error_response(
            request,
            code="INTERNAL_ERROR",
            message=_INTERNAL_MESSAGE,
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            retryable=True,
        )


def require_permission_error(permission: str) -> AuthError:
    """Return the canonical forbidden error for a missing permission."""
    return AuthError("FORBIDDEN", "当前账号没有执行该操作的权限。")


__all__ = [
    "AuthError",
    "ToolError",
    "auth_error_response",
    "error_response",
    "install_exception_handlers",
    "require_permission_error",
    "tool_error_response",
]
