"""FastAPI application factory and runtime entry point."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from redis.asyncio import Redis

from shopmate_ecommerce_assistant.api import (
    admin,
    auth,
    catalog,
    chat,
    conversations,
    handoff,
    orders,
    returns,
    support,
    system,
)
from shopmate_ecommerce_assistant.api.envelope import ErrorEnvelope
from shopmate_ecommerce_assistant.api.errors import install_exception_handlers
from shopmate_ecommerce_assistant.api.health import (
    InfrastructureReadinessChecker,
    ReadinessChecker,
)
from shopmate_ecommerce_assistant.api.health import (
    router as health_router,
)
from shopmate_ecommerce_assistant.api.middleware import RequestIDMiddleware
from shopmate_ecommerce_assistant.core.config import Settings, get_settings
from shopmate_ecommerce_assistant.core.rate_limit import RedisRateLimiter
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory

logger = logging.getLogger(__name__)

_OPENAPI_TAGS = [
    {"name": "health", "description": "存活与就绪探针。"},
    {"name": "auth", "description": "验证码、注册、登录、刷新与退出（JWT + 刷新令牌轮换）。"},
    {"name": "system", "description": "系统元信息。"},
    {"name": "conversations", "description": "会话的创建、重命名、软删除与历史消息。"},
    {
        "name": "chat",
        "description": "SSE 流式聊天（meta/tool_status/product_card/citation/delta/done/error）。",
    },
    {"name": "products", "description": "商品搜索、详情与对比。"},
    {"name": "orders", "description": "订单列表、详情与物流。"},
    {"name": "returns", "description": "退货资格检查与退货申请。"},
    {"name": "handoff", "description": "人工工单（消费者侧）。"},
    {"name": "admin", "description": "管理端知识库、文档上传、chunk 编辑与评测。"},
    {"name": "support", "description": "客服工作台：工单队列、会话取证、状态流转与质量标记。"},
]


def _build_policy_factory(
    settings: Settings,
) -> tuple[Callable[[Any], Any], Any, Any] | None:
    """Wire the stage-7 retriever into a per-request ``PolicyQAService`` factory.

    The expensive singletons (BGE-M3 provider, Milvus client, answer model) are built once
    and shared; only the PostgreSQL authorizer is bound to the session of the request being
    served, because ``POST /chat/stream`` opens a fresh session per stream. Construction is
    lazy and network-free (the Milvus client connects on first search and the model loads on
    first embed), so a missing weight or an enabled-but-unregistered reranker is caught here
    and degrades the chat path to its fixed "知识库暂不可用" answer instead of crashing.

    Returns:
        ``(build_policy, milvus_store, embedder)`` or ``None`` when wiring failed. The
        embedder is returned so the admin ingestion runner reuses one BGE-M3 instance
        instead of loading a second copy of the weights.
    """
    # Imported lazily so importing the app never pulls torch / FlagEmbedding / pymilvus.
    from shopmate_ecommerce_assistant.rag.embeddings import get_bge_m3_provider
    from shopmate_ecommerce_assistant.rag.milvus_store import build_store
    from shopmate_ecommerce_assistant.rag.policy_qa import PolicyQAService, build_answer_model
    from shopmate_ecommerce_assistant.rag.rerank import build_reranker
    from shopmate_ecommerce_assistant.rag.retrieval import DocumentRetriever, session_authorizer

    try:
        provider = get_bge_m3_provider(settings)
        store = build_store(settings)
        reranker = build_reranker(settings)
        answer_model = build_answer_model(settings)
    except Exception:
        logger.exception("RAG wiring failed; policy answers will report unavailable")
        return None

    def build(session: Any) -> Any:
        retriever = DocumentRetriever(
            settings=settings,
            provider=provider,
            store=store,
            authorizer=session_authorizer(session),
            reranker=reranker,
        )
        return PolicyQAService(retriever=retriever, answer_model=answer_model, settings=settings)

    return build, store, provider


def _build_ingestion_runner(
    *,
    settings: Settings,
    embedder: Any,
    store: Any,
    session_factory: Any,
) -> Callable[[Any], Any]:
    """Return a background task that re-parses one queued knowledge version.

    Only built when the RAG wiring succeeded, i.e. when this process can actually load
    BGE-M3. Without it the admin upload/reindex endpoints leave the job ``queued`` — the
    durable record that a worker still has to pick it up — instead of claiming success.
    """

    async def run(version_id: Any) -> None:
        from shopmate_ecommerce_assistant.rag.ingest.worker import run_ingestion_job

        try:
            outcome = await run_ingestion_job(
                session_factory=session_factory,
                settings=settings,
                embedder=embedder,
                store=store,
                version_id=version_id,
            )
        except Exception:
            logger.exception("knowledge ingestion job failed for version %s", version_id)
            return
        if outcome is not None:
            logger.info(
                "knowledge version %s ingestion finished with status %s",
                version_id,
                outcome.status,
            )

    return run


def _install_contract_openapi(app: FastAPI) -> None:
    """Make the generated OpenAPI schema match the responses actually returned.

    FastAPI defaults disagree with ``docs/06-api.md`` in three places:

    * request-validation failures are documented as ``422`` while the global handler renders
      ``400`` + ``VALIDATION_ERROR`` (sections 3.3 and 14);
    * ``POST /chat/stream`` streams ``text/event-stream``, not JSON;
    * authenticated operations do not declare the unified ``401``/``403`` envelopes.

    All three are rewritten here so the published schema stays a usable client contract.
    """
    original_openapi = app.openapi

    def contract_openapi() -> dict[str, Any]:
        schema = original_openapi()
        schemas = schema.setdefault("components", {}).setdefault("schemas", {})
        error_schema = ErrorEnvelope.model_json_schema(ref_template="#/components/schemas/{model}")
        definitions = error_schema.pop("$defs", {})
        schemas.update(definitions)
        schemas["ErrorEnvelope"] = error_schema
        error_content = {
            "application/json": {"schema": {"$ref": "#/components/schemas/ErrorEnvelope"}}
        }

        for methods in schema.get("paths", {}).values():
            for operation in methods.values():
                if not isinstance(operation, dict):
                    continue
                responses = operation.get("responses")
                if not isinstance(responses, dict):
                    continue
                if "422" in responses:
                    responses["400"] = {
                        "description": "请求参数不合法（VALIDATION_ERROR）。",
                        "content": error_content,
                    }
                    del responses["422"]
                if operation.get("security"):
                    responses.setdefault(
                        "401",
                        {
                            "description": "缺少或无效的访问令牌（UNAUTHENTICATED）。",
                            "content": error_content,
                        },
                    )
                    responses.setdefault(
                        "403",
                        {
                            "description": "角色、权限或 CSRF 校验失败。",
                            "content": error_content,
                        },
                    )

        stream = schema.get("paths", {}).get("/api/v1/chat/stream", {}).get("post")
        if isinstance(stream, dict) and isinstance(stream.get("responses"), dict):
            stream["responses"]["200"] = {
                "description": (
                    "SSE 事件流：meta / tool_status / product_card / citation / delta / "
                    "done / error；sequence 从 1 单调递增，且只有一个终止事件。"
                ),
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
            }
        return schema

    app.openapi = contract_openapi


def create_app(
    settings: Settings | None = None,
    *,
    readiness_checker: ReadinessChecker | None = None,
) -> FastAPI:
    """Create a FastAPI app with optional test doubles for readiness checks."""
    resolved_settings = settings or get_settings()
    # Fail fast instead of serving production traffic with the published dev secrets.
    resolved_settings.ensure_production_secrets()
    logging.basicConfig(level=resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(resolved_settings)
        redis = Redis.from_url(resolved_settings.redis_url, decode_responses=True)
        http_client = httpx.AsyncClient(timeout=resolved_settings.readiness_timeout_seconds)

        app.state.settings = resolved_settings
        app.state.engine = engine
        app.state.redis = redis
        app.state.http_client = http_client
        app.state.session_factory = create_session_factory(engine)
        app.state.rate_limiter = RedisRateLimiter(redis)
        # Stage 5/7 RAG wired into the chat path. ``policy_factory`` builds a
        # ``PolicyQAService`` bound to the session of the request being served and is what
        # ``POST /chat/stream`` uses; ``policy`` remains available as a static override for
        # tests. If wiring failed both stay unset and the chat service answers with its
        # fixed "知识库暂不可用" message instead of guessing.
        app.state.policy = None
        app.state.policy_store = None
        wiring = _build_policy_factory(resolved_settings)
        app.state.ingestion_runner = None
        if wiring is not None:
            app.state.policy_factory, app.state.policy_store, embedder = wiring
            app.state.ingestion_runner = _build_ingestion_runner(
                settings=resolved_settings,
                embedder=embedder,
                store=app.state.policy_store,
                session_factory=app.state.session_factory,
            )
        else:
            app.state.policy_factory = None
        app.state.readiness_checker = readiness_checker or InfrastructureReadinessChecker(
            engine=engine,
            redis=redis,
            http_client=http_client,
            milvus_health_url=resolved_settings.milvus_health_url,
            timeout_seconds=resolved_settings.readiness_timeout_seconds,
        )

        try:
            yield
        finally:
            policy_store = getattr(app.state, "policy_store", None)
            if policy_store is not None:
                try:
                    policy_store.close()
                except Exception:  # pragma: no cover - driver-specific shutdown
                    logger.warning("Milvus client close failed during shutdown")
            await http_client.aclose()
            await redis.aclose()
            await engine.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        description=(
            "ShopMate 电商智能客服 API。统一响应信封、JWT 认证、SSE 流式聊天、"
            "确定性工具层与租户/归属隔离。契约见 docs/06-api.md。"
        ),
        openapi_tags=_OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )
    install_exception_handlers(app)
    _install_contract_openapi(app)

    # Host header allow-list (production). Disabled by default so local runs and the
    # test suite keep working; compose.prod.yaml sets TRUSTED_HOSTS to the public domain.
    if resolved_settings.allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=resolved_settings.allowed_hosts,
        )

    app.include_router(health_router)
    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(conversations.router)
    app.include_router(chat.router)
    app.include_router(catalog.router)
    app.include_router(orders.router)
    app.include_router(returns.router)
    app.include_router(handoff.router)
    app.include_router(admin.router)
    app.include_router(support.router)
    return app


app = create_app()


def run() -> None:
    """Run the API for the CLI entry point with reload disabled."""
    uvicorn.run(
        "shopmate_ecommerce_assistant.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
