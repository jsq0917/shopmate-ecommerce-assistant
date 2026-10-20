"""Unified error envelope and exception handler tests."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from shopmate_ecommerce_assistant.api.errors import (
    auth_error_response,
    error_response,
    install_exception_handlers,
    tool_error_response,
)
from shopmate_ecommerce_assistant.api.middleware import RequestIDMiddleware
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.security import AuthError


def _make_app(raises) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    install_exception_handlers(app)

    @app.get("/boom")
    async def boom(request: Request):
        raise raises()

    return app


def test_tool_error_maps_to_status_and_envelope() -> None:
    app = _make_app(lambda: ToolError(ErrorCode.PRODUCT_NOT_FOUND, "未找到该商品。"))

    with TestClient(app) as client:
        response = client.get("/boom")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert body["error"]["message"] == "未找到该商品。"
    assert body["error"]["retryable"] is False
    assert "request_id" in body
    assert "trace_id" in body


def test_auth_error_maps_to_401() -> None:
    app = _make_app(lambda: AuthError("UNAUTHENTICATED", "请先登录后再访问。"))

    with TestClient(app) as client:
        response = client.get("/boom")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_rate_limited_maps_to_429_with_retry_after() -> None:
    app = _make_app(
        lambda: ToolError(
            ErrorCode.RATE_LIMITED,
            "请求过于频繁。",
            retryable=True,
            retry_after_ms=5000,
        )
    )

    with TestClient(app) as client:
        response = client.get("/boom")

    assert response.status_code == 429
    assert response.json()["error"]["retryable"] is True
    assert response.json()["error"]["retry_after_ms"] == 5000


def test_unhandled_exception_is_generic_500_without_leak() -> None:
    app = _make_app(lambda: RuntimeError("postgresql://user:secret@db/internal"))

    # Starlette's ServerErrorMiddleware always re-raises after sending the 500; suppress
    # that so we can assert on the returned envelope instead of the re-raised exception.
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "postgresql://" not in response.text
    assert "secret" not in response.text


def test_validation_error_maps_to_400() -> None:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    install_exception_handlers(app)

    from pydantic import BaseModel

    class Body(BaseModel):
        required: str

    @app.post("/validate")
    async def validate(body: Body):
        return {"ok": True}

    with TestClient(app) as client:
        response = client.post("/validate", json={})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_error_response_directly_builds_envelope() -> None:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/direct")
    async def direct(request: Request):
        return error_response(request, code="FORBIDDEN", message="无权访问。", http_status=403)

    with TestClient(app) as client:
        response = client.get("/direct")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_tool_error_response_uses_unknown_code_as_400() -> None:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/unknown")
    async def unknown(request: Request):
        return tool_error_response(request, ToolError(ErrorCode.INTERNAL_ERROR, "boom"))

    with TestClient(app) as client:
        response = client.get("/unknown")

    assert response.status_code == 500


def test_auth_error_response_csrf_maps_to_403() -> None:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/csrf")
    async def csrf(request: Request):
        return auth_error_response(request, AuthError("CSRF_INVALID", "会话校验失败。"))

    with TestClient(app) as client:
        response = client.get("/csrf")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_INVALID"
