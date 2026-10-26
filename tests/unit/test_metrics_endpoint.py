"""``GET /metrics``: Prometheus exposure with optional static-token auth.

``METRICS_TOKEN`` is the protection for environments where the API port is reachable
beyond loopback (Prometheus scrapers carry no session cookie, so the business JWT does
not apply). An empty token keeps the endpoint open — a local-development convenience
that must never leak into a shared deployment.
"""

from __future__ import annotations

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.observability.metrics import chat_turns, make_router

#: The registry is process-global and the full suite shares one pytest process, so the
#: probe uses label values no other test touches and the assertion checks that the
#: series *exists* with a numeric value — never an exact count.
_PROBE_INTENT = "__probe_intent_metrics__"


def _client(token: str) -> TestClient:
    settings = Settings(_env_file=None, metrics_token=token)  # type: ignore[call-arg]
    app = FastAPI()
    app.include_router(make_router(settings))
    return TestClient(app)


def _metrics_body(client: TestClient) -> str:
    chat_turns.labels(_PROBE_INTENT, "stop").inc()
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    return response.text


def test_open_endpoint_without_token_serves_metrics() -> None:
    body = _metrics_body(_client(""))
    assert "shopmate_chat_turns_total" in body
    series = rf'shopmate_chat_turns_total\{{finish_reason="stop",intent="{_PROBE_INTENT}"\}}'
    assert re.search(rf"{series} \d+(\.\d+)?", body)


def test_configured_token_is_required() -> None:
    client = _client("s3cret-token")

    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"X-Metrics-Token": "wrong"}).status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401

    ok_header = client.get("/metrics", headers={"X-Metrics-Token": "s3cret-token"})
    assert ok_header.status_code == 200
    ok_bearer = client.get("/metrics", headers={"Authorization": "Bearer s3cret-token"})
    assert ok_bearer.status_code == 200
    assert "shopmate_chat_turns_total" in ok_bearer.text
