"""Deterministic chat orchestration tests (no database).

``ChatService._run`` is the turn's decision core: it takes a pre-computed route and a
server-built :class:`ToolContext` and returns the outcome without touching the database.
A fake dispatcher supplies tool results so the success, clarification and failure paths
can be exercised in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from shopmate_ecommerce_assistant.agents.chat_service import UPSTREAM_TEXT, ChatService
from shopmate_ecommerce_assistant.agents.router import route_intent
from shopmate_ecommerce_assistant.agents.sse import EVENT_PRODUCT_CARD, EVENT_TOOL_STATUS
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.db.models.enums import UserRole
from shopmate_ecommerce_assistant.rag.errors import RetrievalError
from shopmate_ecommerce_assistant.rag.policy_qa import AnswerModelError
from shopmate_ecommerce_assistant.tools.context import RiskContext, ToolContext
from shopmate_ecommerce_assistant.tools.schemas import ToolFailure, ToolSuccess


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


def _tool_context() -> ToolContext:
    return ToolContext(
        shop_id=uuid4(),
        actor_user_id=uuid4(),
        role=UserRole.SHOPPER,
        request_id=uuid4(),
        trace_id=uuid4(),
        conversation_id=uuid4(),
        risk_context=RiskContext(),
    )


class FakeDispatcher:
    """Returns a canned result and records every invocation."""

    def __init__(self, result: ToolSuccess | ToolFailure) -> None:
        self._result = result
        self.calls: list[tuple[str, Any, ToolContext]] = []

    async def invoke(self, tool_name: str, payload: Any, *, context: ToolContext):
        self.calls.append((tool_name, payload, context))
        return self._result


class FailingPolicy:
    """Raises the injected dependency failure (model timeout / retrieval outage)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def answer(self, question, scope, *, query_plan=None):
        raise self._exc


def _success(data: dict[str, Any]) -> ToolSuccess:
    return ToolSuccess(
        tool_call_id=uuid4(),
        data=data,
        as_of=datetime.now(UTC),
        trace_id=uuid4(),
    )


def _failure(code: ErrorCode, message: str = "失败") -> ToolFailure:
    return ToolFailure(
        tool_call_id=uuid4(),
        error_code=code.value,
        user_message=message,
        trace_id=uuid4(),
    )


def _service(dispatcher, settings: Settings, *, policy=None) -> ChatService:
    return ChatService(session=None, settings=settings, dispatcher=dispatcher, policy=policy)


def _route(text: str, settings: Settings):
    return route_intent(text, settings=settings)


async def test_smalltalk_returns_safe_reply_without_tools(settings: Settings) -> None:
    dispatcher = FakeDispatcher(_success({}))
    service = _service(dispatcher, settings)
    route = _route("你好", settings)

    outcome = await service._run(route, "你好", _tool_context())

    assert "你好" in outcome.answer_text
    assert outcome.structured_facts_verified is True
    assert dispatcher.calls == []  # no tool was invoked


async def test_policy_without_service_refuses_grounded_answer(settings: Settings) -> None:
    service = _service(FakeDispatcher(_success({})), settings)
    route = _route("七天无理由退货的政策是什么？", settings)

    outcome = await service._run(route, "七天无理由退货的政策是什么？", _tool_context())

    assert "知识库" in outcome.answer_text
    assert outcome.structured_facts_verified is False  # not grounded, no evidence


async def test_product_discovery_success_emits_tool_status_and_cards(settings: Settings) -> None:
    dispatcher = FakeDispatcher(
        _success(
            {
                "items": [
                    {
                        "product_id": str(uuid4()),
                        "variant_id": str(uuid4()),
                        "title": "降噪耳机 Pro",
                        "price_cents": 29900,
                        "currency": "CNY",
                        "stock_status": "in_stock",
                        "available_qty": 5,
                        "attributes": {},
                        "matched_reasons": ["推荐"],
                        "is_synthetic": True,
                        "as_of": datetime.now(UTC).isoformat(),
                    }
                ]
            }
        )
    )
    service = _service(dispatcher, settings)
    route = _route("帮我推荐一款降噪耳机", settings)

    outcome = await service._run(route, "帮我推荐一款降噪耳机", _tool_context())

    assert "降噪耳机 Pro" in outcome.answer_text
    assert "¥299" in outcome.answer_text
    types = [event.type for event in outcome.pre_events]
    assert EVENT_TOOL_STATUS in types
    assert EVENT_PRODUCT_CARD in types
    assert dispatcher.calls[0][0] == "search_products"


async def test_product_discovery_tool_failure_becomes_tool_error(settings: Settings) -> None:
    dispatcher = FakeDispatcher(_failure(ErrorCode.UPSTREAM_UNAVAILABLE, "上游暂不可用"))
    service = _service(dispatcher, settings)
    route = _route("帮我推荐一款降噪耳机", settings)

    with pytest.raises(ToolError) as exc:
        await service._run(route, "帮我推荐一款降噪耳机", _tool_context())

    assert exc.value.code is ErrorCode.UPSTREAM_UNAVAILABLE


async def test_order_status_without_order_number_clarifies(settings: Settings) -> None:
    dispatcher = FakeDispatcher(_success({}))
    service = _service(dispatcher, settings)
    route = _route("查询一下我的订单状态", settings)

    outcome = await service._run(route, "查询一下我的订单状态", _tool_context())

    assert "订单号" in outcome.answer_text
    assert dispatcher.calls == []  # it asks instead of guessing an order


async def test_return_without_order_item_clarifies(settings: Settings) -> None:
    dispatcher = FakeDispatcher(_success({}))
    service = _service(dispatcher, settings)
    route = _route("我要退货", settings)

    outcome = await service._run(route, "我要退货", _tool_context())

    assert "退货" in outcome.answer_text
    # It queries the order (if an order number was present) but never fabricates a write.
    assert all(call[0] != "create_return_request" for call in dispatcher.calls)


async def test_complaint_handoff_creates_ticket(settings: Settings) -> None:
    ticket_id = str(uuid4())
    dispatcher = FakeDispatcher(
        _success({"ticket_id": ticket_id, "risk_level": "high", "priority": "P1"})
    )
    service = _service(dispatcher, settings)
    route = _route("我要投诉你们", settings)

    outcome = await service._run(route, "我要投诉你们", _tool_context())

    assert ticket_id in outcome.answer_text
    assert outcome.finish_reason == "handoff"
    assert dispatcher.calls[0][0] == "create_handoff_ticket"


async def test_compare_without_two_products_clarifies(settings: Settings) -> None:
    dispatcher = FakeDispatcher(_success({}))
    service = _service(dispatcher, settings)
    route = _route("这两款有什么区别", settings)

    outcome = await service._run(route, "这两款有什么区别", _tool_context())

    assert "对比" in outcome.answer_text
    assert dispatcher.calls == []


async def test_policy_model_timeout_degrades_to_unavailable(settings: Settings) -> None:
    question = "七天无理由退货的政策是什么？"
    policy = FailingPolicy(AnswerModelError("ANSWER_MODEL_TIMEOUT", "回答模型超时"))
    service = _service(FakeDispatcher(_success({})), settings, policy=policy)
    route = _route(question, settings)

    outcome = await service._run(route, question, _tool_context())

    assert outcome.answer_text == UPSTREAM_TEXT
    assert outcome.structured_facts_verified is False
    assert outcome.citations == []
    assert outcome.pre_events == []


async def test_policy_retrieval_failure_degrades_to_unavailable(settings: Settings) -> None:
    question = "七天无理由退货的政策是什么？"
    policy = FailingPolicy(RetrievalError("MILVUS_UNAVAILABLE", "向量库不可用", retryable=True))
    service = _service(FakeDispatcher(_success({})), settings, policy=policy)
    route = _route(question, settings)

    outcome = await service._run(route, question, _tool_context())

    assert outcome.answer_text == UPSTREAM_TEXT
    assert outcome.structured_facts_verified is False
    # A retrieval outage must never be dressed up as a grounded answer.
    assert outcome.citation_labels == []
