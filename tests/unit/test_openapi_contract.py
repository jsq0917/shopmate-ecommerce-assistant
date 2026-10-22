"""OpenAPI contract tests: the published schema must match the implemented responses.

``docs/06-api.md`` fixes request-validation failures at HTTP 400 (sections 3.3 and 14) and
the chat stream at ``text/event-stream`` (section 7.1); FastAPI's defaults are 422 and
``application/json``. ``main._install_contract_openapi`` rewrites them, and these tests pin
that behaviour so the schema stays a usable client contract.
"""

from __future__ import annotations

from shopmate_ecommerce_assistant.main import create_app

_ENVELOPE_REF = {"$ref": "#/components/schemas/ErrorEnvelope"}


def _schema() -> dict:
    app = create_app()
    return app.openapi()


def _operations(schema: dict) -> list[tuple[str, str, dict]]:
    operations = []
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if isinstance(operation, dict) and "responses" in operation:
                operations.append((method.upper(), path, operation))
    return operations


def test_openapi_exposes_the_full_surface() -> None:
    schema = _schema()
    operations = _operations(schema)
    assert len(schema["paths"]) == 43
    assert len(operations) == 52
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"


def test_no_operation_declares_the_fastapi_default_422() -> None:
    schema = _schema()
    offenders = [
        (method, path)
        for method, path, operation in _operations(schema)
        if "422" in operation["responses"]
    ]
    assert offenders == []


def test_validation_failures_are_400_with_the_unified_error_envelope() -> None:
    schema = _schema()
    checked = 0
    for method, path, operation in _operations(schema):
        bad_request = operation["responses"].get("400")
        if bad_request is None:
            continue
        checked += 1
        assert bad_request["content"]["application/json"]["schema"] == _ENVELOPE_REF, (
            f"{method} {path} 400 does not use the error envelope"
        )
    assert checked >= 20, "expected every parameterised operation to declare 400"


def test_chat_stream_declares_event_stream_not_json() -> None:
    schema = _schema()
    stream = schema["paths"]["/api/v1/chat/stream"]["post"]
    content = stream["responses"]["200"]["content"]
    assert set(content) == {"text/event-stream"}
    assert "application/json" not in content


def test_authenticated_operations_declare_401_and_403() -> None:
    schema = _schema()
    authenticated = 0
    for method, path, operation in _operations(schema):
        if not operation.get("security"):
            continue
        authenticated += 1
        assert "401" in operation["responses"], f"{method} {path} misses 401"
        assert "403" in operation["responses"], f"{method} {path} misses 403"
    # 43 operations minus the 8 unauthenticated ones (captcha/register/login/refresh/
    # logout, health, ready, system/meta).
    assert authenticated == 44


def test_unauthenticated_operations_declare_no_auth_failures() -> None:
    schema = _schema()
    for path in ("/health", "/ready", "/api/v1/system/meta", "/api/v1/auth/captcha"):
        operation = schema["paths"][path]["get"]
        assert not operation.get("security")
        assert "401" not in operation["responses"]
        assert "403" not in operation["responses"]


def test_error_envelope_components_are_registered_and_referenced() -> None:
    schema = _schema()
    schemas = schema["components"]["schemas"]
    assert "ErrorEnvelope" in schemas
    assert "ErrorBody" in schemas
    dumped = str(schema)
    assert "#/components/schemas/ErrorEnvelope" in dumped
    # No dangling Pydantic $defs references left behind by the schema rewrite.
    assert "#/$defs/" not in dumped


def test_openapi_is_stable_across_calls() -> None:
    app = create_app()
    first = app.openapi()
    second = app.openapi()
    assert first == second
    assert "422" not in str(second)
