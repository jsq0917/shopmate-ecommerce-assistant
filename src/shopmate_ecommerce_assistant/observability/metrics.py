"""Prometheus metrics registry and a FastAPI router exposing ``/metrics``.

The registry is a process-wide singleton created lazily. Every counter/histogram is
defined here so label names stay consistent across the codebase; callers import the
instruments and call ``.inc()`` / ``.observe()`` rather than building ad-hoc labels.

In production the endpoint must be protected: either set ``METRICS_TOKEN`` (checked by
:func:`make_router`) or keep the API port off the public network behind a
reverse-proxy allowlist. Prometheus scrapers carry no session cookie, hence the static
token instead of the JWT the business APIs use.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

from shopmate_ecommerce_assistant.core.config import Settings, get_settings

#: Single shared registry. The default registry is avoided so embedding this app in a
#: larger process does not leak metrics from other libraries.
_REGISTRY = CollectorRegistry()

# -- chat turn pipeline -------------------------------------------------------
chat_turns = Counter(
    "shopmate_chat_turns_total",
    "Chat turns completed, by intent and finish reason.",
    ["intent", "finish_reason"],
    registry=_REGISTRY,
)

chat_latency_seconds = Histogram(
    "shopmate_chat_latency_seconds",
    "End-to-end chat turn latency in seconds.",
    ["intent"],
    registry=_REGISTRY,
)

# -- LLM ----------------------------------------------------------------------
llm_tokens = Counter(
    "shopmate_llm_tokens_total",
    "LLM tokens consumed, by prompt/completion.",
    ["model", "kind"],
    registry=_REGISTRY,
)

llm_latency_seconds = Histogram(
    "shopmate_llm_latency_seconds",
    "LLM round-trip latency.",
    ["model"],
    registry=_REGISTRY,
)

# -- retrieval ----------------------------------------------------------------
retrieval_latency_seconds = Histogram(
    "shopmate_retrieval_latency_seconds",
    "Knowledge retrieval latency.",
    ["mode"],
    registry=_REGISTRY,
)

# -- handoff / safety ---------------------------------------------------------
handoff_total = Counter(
    "shopmate_handoff_total",
    "Turns escalated to human support, by reason code.",
    ["reason_code"],
    registry=_REGISTRY,
)

refusal_total = Counter(
    "shopmate_refusal_total",
    "Turns refused for lack of evidence.",
    ["reason"],
    registry=_REGISTRY,
)


def registry() -> CollectorRegistry:
    """Return the shared metrics registry."""
    return _REGISTRY


def make_router(settings: Settings | None = None) -> APIRouter:
    """Build the ``/metrics`` router. Hidden from OpenAPI because it is scraped by
    Prometheus, not called by the frontend.

    Authentication: when ``settings.metrics_token`` is non-empty the request must carry it
    either in the ``X-Metrics-Token`` header or as ``Authorization: Bearer <token>``;
    anything else gets ``401``. An empty token keeps the endpoint open — that is a local
    development convenience, and in that mode the API port must stay on loopback.
    """
    resolved = settings or get_settings()
    router = APIRouter(tags=["metrics"], include_in_schema=False)

    @router.get("/metrics")
    def metrics(request: Request) -> Response:
        token = resolved.metrics_token
        if token:
            supplied = request.headers.get("x-metrics-token") or ""
            if not supplied:
                authorization = request.headers.get("authorization") or ""
                supplied = authorization.removeprefix("Bearer ").removeprefix("bearer ")
            if not hmac.compare_digest(supplied, token):
                return Response(
                    status_code=401,
                    content="unauthorized\n",
                    media_type="text/plain; charset=utf-8",
                )
        return Response(content=generate_latest(_REGISTRY), media_type=CONTENT_TYPE_LATEST)

    return router


__all__ = [
    "chat_latency_seconds",
    "chat_turns",
    "handoff_total",
    "llm_latency_seconds",
    "llm_tokens",
    "make_router",
    "refusal_total",
    "registry",
    "retrieval_latency_seconds",
]
