"""故障演练：依赖不可用、模型超时、检索为空与工具失败（阶段 12）。

Every drill injects the failure at the narrowest seam that a real outage would hit, then
asserts the *contract* the safety document requires (docs/07-security.md §14):

* a stable, Chinese, actionable message reaches the caller;
* no SQL, connection string, stack trace, token or PII leaks into the response or the log;
* a real-time fact is never invented when its source is unavailable;
* failures do not loop: one turn stops after the first failed tool call.

No Docker container is stopped here: the point is to prove the code paths, not to disturb
the running stack.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from shopmate_ecommerce_assistant.agents.chat_service import (
    POLICY_UNAVAILABLE_TEXT,
    ChatService,
)
from shopmate_ecommerce_assistant.agents.router import route_intent
from shopmate_ecommerce_assistant.api.errors import install_exception_handlers
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.errors import ErrorCode
from shopmate_ecommerce_assistant.core.rate_limit import InMemoryRateLimiter
from shopmate_ecommerce_assistant.core.security import (
    AccessContext,
    issue_access_token,
    permissions_for,
)
from shopmate_ecommerce_assistant.db.models.enums import UserRole
from shopmate_ecommerce_assistant.rag.policy_qa import (
    REFUSAL_TEXT,
    AnswerModelError,
    OpenAICompatibleAnswerModel,
    PolicyQAService,
)
from shopmate_ecommerce_assistant.rag.retrieval import (
    RetrievalMode,
    RetrievalResult,
    RetrievalScope,
)
from shopmate_ecommerce_assistant.tools.context import RiskContext, ToolContext
from shopmate_ecommerce_assistant.tools.runtime import (
    INTERNAL_MESSAGE,
    UPSTREAM_MESSAGE,
    ToolOutcome,
    ToolRuntime,
)
from shopmate_ecommerce_assistant.tools.schemas import ToolFailure

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")


# --------------------------------------------------------------------------- helpers


def _settings() -> Settings:
    return Settings(_env_file=None, jwt_secret="fault-drill-secret")


def _tool_context() -> ToolContext:
    return ToolContext(
        shop_id=SHOP_ID,
        actor_user_id=USER_ID,
        role=UserRole.SHOPPER,
        request_id=uuid4(),
        trace_id=uuid4(),
        conversation_id=uuid4(),
        risk_context=RiskContext(),
    )


def _assert_safe_message(message: str, *, forbidden: tuple[str, ...] = ()) -> None:
    """A user-facing failure message must be Chinese prose with no internals."""
    assert message.strip()
    assert any("\u4e00" <= char <= "\u9fff" for char in message), f"不是中文提示：{message!r}"
    lowered = message.lower()
    tokens = ("select ", "insert ", "postgres", "traceback", "operationalerror", *forbidden)
    for token in tokens:
        assert token not in lowered, f"失败信息泄露内部细节：{token}"


class _RaisingDispatcher:
    """Counts invocations and always fails, like an upstream tool outage."""

    def __init__(self, failure: ToolFailure) -> None:
        self._failure = failure
        self.calls = 0

    async def invoke(self, tool_name: str, payload: Any, *, context: ToolContext):
        self.calls += 1
        return self._failure


class _EmptyRetriever:
    """Retriever returning no evidence (empty index / all candidates filtered out)."""

    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(self, query: str, scope: RetrievalScope) -> RetrievalResult:
        self.calls += 1
        return RetrievalResult(
            query=query,
            scope=scope,
            mode=RetrievalMode.HYBRID,
            evidence=(),
            citations=(),
            evidence_sufficient=False,
            top_dense_similarity=None,
            audit={"rejected": {}},
        )


class _ExplodingSessionFactory:
    """A session factory that fails the way a dead PostgreSQL would."""

    def __call__(self):
        raise OperationalError(
            "SELECT 1", {"phone": "13800138000"}, Exception("connection refused to 127.0.0.1:5432")
        )


class _ExplodingLimiter(InMemoryRateLimiter):
    """A limiter whose Redis backend is unreachable."""

    async def check(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, float]:
        raise ConnectionError("Error 111 connecting to redis:6379")


# ------------------------------------------------------------------- 工具层依赖故障


async def test_tool_database_outage_maps_to_a_stable_upstream_error() -> None:
    """PostgreSQL down during a read tool -> UPSTREAM_UNAVAILABLE, never a stack trace."""

    async def handler(payload: Any, context: ToolContext) -> ToolOutcome:
        raise OperationalError(
            "SELECT * FROM orders", {"address": "上海市浦东新区张江路 100 号"}, Exception("down")
        )

    result = await ToolRuntime().execute(
        "get_order_status", context=_tool_context(), payload={}, handler=handler
    )

    assert isinstance(result, ToolFailure)
    assert result.error_code == ErrorCode.UPSTREAM_UNAVAILABLE.value
    assert result.retryable is True
    assert result.user_message == UPSTREAM_MESSAGE
    _assert_safe_message(result.user_message, forbidden=("13800138000", "张江路"))


async def test_tool_unexpected_error_does_not_echo_the_exception() -> None:
    """An unexpected exception is mapped to a fixed message; its text is not forwarded."""

    async def handler(payload: Any, context: ToolContext) -> ToolOutcome:
        raise RuntimeError("upstream said: user 13800138000 lives at 张江路 100 号")

    result = await ToolRuntime().execute(
        "search_products", context=_tool_context(), payload={}, handler=handler
    )

    assert isinstance(result, ToolFailure)
    assert result.error_code == ErrorCode.INTERNAL_ERROR.value
    assert result.user_message == INTERNAL_MESSAGE
    _assert_safe_message(result.user_message, forbidden=("13800138000", "张江路"))


# --------------------------------------------------------------------- 模型与检索故障


def test_model_timeout_becomes_answer_model_unavailable() -> None:
    """An LLM timeout (httpx timeout) must surface as a stable, non-fabricating error."""
    settings = Settings(
        _env_file=None,
        llm_base_url="http://llm.invalid/v1",
        llm_model="fake-model",
        llm_api_key="sk-test-placeholder",
    )
    model = OpenAICompatibleAnswerModel(settings)

    with patch("httpx.Client.post", side_effect=httpx.ReadTimeout("timed out")):
        with pytest.raises(AnswerModelError) as info:
            model.complete(system="s", user="u")

    assert info.value.code == "ANSWER_MODEL_UNAVAILABLE"
    _assert_safe_message(str(info.value))


async def test_empty_retrieval_refuses_without_calling_the_model() -> None:
    """检索为空时必须拒答；不得调用模型，也不得返回引用。"""
    retriever = _EmptyRetriever()

    class _ForbiddenModel:
        calls = 0

        def complete(  # pragma: no cover - guard
            self, *, system: str, user: str, generation=None
        ) -> str:
            self.calls += 1
            return "自编政策 [c1]"

    model = _ForbiddenModel()
    service = PolicyQAService(
        retriever=retriever,  # type: ignore[arg-type]
        answer_model=model,
        settings=_settings(),
    )

    answer = await service.answer(
        "七天无理由退货的政策是什么？", RetrievalScope(shop_id=str(SHOP_ID))
    )

    assert answer.status == "refused"
    assert answer.answer_text == REFUSAL_TEXT
    assert answer.citations == ()
    assert model.calls == 0, "无证据时不得调用回答模型"


async def test_policy_answer_without_a_configured_model_degrades_to_unavailable() -> None:
    """No LLM configured: the chat turn reports unavailability instead of inventing text."""
    service = ChatService(
        session=None,
        settings=_settings(),
        dispatcher=_RaisingDispatcher(
            ToolFailure(
                tool_call_id=uuid4(),
                error_code=ErrorCode.INTERNAL_ERROR.value,
                user_message="unused",
                trace_id=uuid4(),
            )
        ),
        policy=None,
    )
    outcome = await service._run(  # noqa: SLF001 - the drill targets this branch
        route_intent("七天无理由退货的政策是什么？", settings=_settings()),
        "七天无理由退货的政策是什么？",
        _tool_context(),
    )
    assert outcome.answer_text == POLICY_UNAVAILABLE_TEXT
    assert outcome.citations == []


# --------------------------------------------------------------------- 工具失败不循环


async def test_tool_failure_stops_the_turn_after_one_call() -> None:
    """§9.3：工具失败不得形成重试循环；本轮以受控 ToolError 结束，消息可读。"""
    from shopmate_ecommerce_assistant.core.errors import ToolError

    failure = ToolFailure(
        tool_call_id=uuid4(),
        error_code=ErrorCode.UPSTREAM_UNAVAILABLE.value,
        user_message=UPSTREAM_MESSAGE,
        retryable=True,
        trace_id=uuid4(),
    )
    dispatcher = _RaisingDispatcher(failure)
    service = ChatService(session=None, settings=_settings(), dispatcher=dispatcher)

    text = "推荐一款降噪耳机"
    with pytest.raises(ToolError) as info:
        await service._run(  # noqa: SLF001 - the drill targets this branch
            route_intent(text, settings=_settings()), text, _tool_context()
        )

    assert dispatcher.calls == 1, "失败后不得自动重试同一工具"
    assert info.value.code is ErrorCode.UPSTREAM_UNAVAILABLE
    assert info.value.retryable is True
    _assert_safe_message(info.value.user_message)


# ----------------------------------------------------------------- API 层依赖故障


def _api_app(*, session_factory, limiter=None):
    from fastapi import FastAPI

    from shopmate_ecommerce_assistant.api import conversations

    app = FastAPI()
    app.state.settings = _settings()
    app.state.session_factory = session_factory
    app.state.rate_limiter = limiter or InMemoryRateLimiter()
    app.state.policy = None
    app.state.policy_factory = None
    install_exception_handlers(app)
    app.include_router(conversations.router)
    from shopmate_ecommerce_assistant.api import chat

    app.include_router(chat.router)
    return app


def _token(settings: Settings) -> str:
    return issue_access_token(
        settings,
        AccessContext(
            shop_id=SHOP_ID,
            user_id=USER_ID,
            role=UserRole.SHOPPER,
            permissions=permissions_for(UserRole.SHOPPER),
        ),
    )


async def test_postgres_outage_returns_a_safe_envelope() -> None:
    """数据库不可用时返回统一错误信封，不泄露连接串、SQL 或参数。"""
    settings = _settings()
    app = _api_app(session_factory=_ExplodingSessionFactory())

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/conversations", headers={"Authorization": f"Bearer {_token(settings)}"}
        )

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["retryable"] is True
    _assert_safe_message(body["error"]["message"], forbidden=("13800138000", "5432"))
    assert "request_id" in body and "trace_id" in body


async def test_redis_outage_in_the_rate_limiter_returns_a_safe_envelope() -> None:
    """Redis 不可用时不得放行，也不得把驱动异常文本返回给客户端（fail-closed）。"""
    settings = _settings()
    app = _api_app(session_factory=_ExplodingSessionFactory(), limiter=_ExplodingLimiter())

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat/stream",
            json={
                "conversation_id": str(uuid4()),
                "message": "你好",
                "client_message_id": str(uuid4()),
            },
            headers={"Authorization": f"Bearer {_token(settings)}"},
        )

    # Availability trade-off is explicit: an unavailable limiter fails closed (5xx) instead
    # of silently allowing unlimited traffic. The client still gets a safe, retryable error.
    assert response.status_code >= 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["retryable"] is True
    _assert_safe_message(body["error"]["message"], forbidden=("redis", "6379", "connection"))


async def test_ready_endpoint_reports_a_dead_dependency_without_detail() -> None:
    """``/ready`` 在依赖不可用时 503，且只返回 ok/error 状态，不含异常文本。"""
    from shopmate_ecommerce_assistant.api.health import router as health_router

    class _Checker:
        async def check(self) -> dict[str, str]:
            return {"postgres": "error", "redis": "ok", "milvus": "ok"}

    from fastapi import FastAPI

    app = FastAPI()
    app.state.readiness_checker = _Checker()
    app.include_router(health_router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"] == {"postgres": "error", "redis": "ok", "milvus": "ok"}


async def test_health_stays_alive_when_every_dependency_is_down() -> None:
    """``/health`` 只表示进程存活：依赖全挂时仍为 200。"""
    from fastapi import FastAPI

    from shopmate_ecommerce_assistant.api.health import router as health_router

    class _Checker:
        async def check(self) -> dict[str, str]:
            return {"postgres": "error", "redis": "error", "milvus": "error"}

    app = FastAPI()
    app.state.readiness_checker = _Checker()
    app.include_router(health_router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/ready")).status_code == 503


# ------------------------------------------------------------------------- 日志脱敏


class _ListHandler(logging.Handler):
    """Collect every formatted record emitted during a drill."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())
        if record.exc_info:
            self.messages.append(logging.Formatter().formatException(record.exc_info))


@pytest.fixture
def captured_logs() -> _ListHandler:
    handler = _ListHandler()
    root = logging.getLogger()
    previous_level = root.level
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


async def test_failure_logs_never_contain_pii_sql_or_credentials(
    captured_logs: _ListHandler,
) -> None:
    """§16.2.13：失败路径的日志只允许稳定文案，不得出现 PII/SQL/连接串/密钥。"""
    phone = "13800138000"
    address = "上海市浦东新区张江路 100 号 3 栋 501 室"

    async def handler(payload: Any, context: ToolContext) -> ToolOutcome:
        raise OperationalError(
            "SELECT * FROM orders WHERE phone = :phone",
            {"phone": phone, "address": address},
            Exception("password authentication failed for user shopmate"),
        )

    async def unexpected(payload: Any, context: ToolContext) -> ToolOutcome:
        raise RuntimeError(f"echo {phone} {address}")

    runtime = ToolRuntime()
    await runtime.execute("get_order_status", context=_tool_context(), payload={}, handler=handler)
    await runtime.execute(
        "search_products", context=_tool_context(), payload={}, handler=unexpected
    )

    joined = "\n".join(captured_logs.messages)
    assert joined, "失败路径必须留下可观测日志"
    for leaked in (
        phone,
        address,
        "张江路",
        "SELECT *",
        "password authentication failed",
        "Bearer ",
        "sk-",
        # AGENTS.md §16.2.13「系统 prompt 不入日志」：提示词标记与证据块标签都不得落盘。
        "你是 ShopMate",
        "<evidence",
        "NO_EVIDENCE",
    ):
        assert leaked not in joined, f"日志泄露了敏感内容：{leaked}"

    # The safe, structured reason is still present for on-call diagnosis.
    assert "database unavailable" in joined
    assert "unexpected error" in joined
