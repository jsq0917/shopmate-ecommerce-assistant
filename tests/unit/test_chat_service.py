"""Deterministic chat orchestration tests (no database).

``ChatService._run`` is the turn's decision core: it takes a pre-computed route and a
server-built :class:`ToolContext` and returns the outcome without touching the database.
A fake dispatcher supplies tool results so the success, clarification and failure paths
can be exercised in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from shopmate_ecommerce_assistant.agents.chat_service import UPSTREAM_TEXT, ChatService
from shopmate_ecommerce_assistant.agents.router import Intent, route_intent
from shopmate_ecommerce_assistant.agents.sse import EVENT_PRODUCT_CARD, EVENT_TOOL_STATUS
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.generation import GenerationParams
from shopmate_ecommerce_assistant.db.models.enums import UserRole
from shopmate_ecommerce_assistant.rag.citations import Citation
from shopmate_ecommerce_assistant.rag.errors import RetrievalError
from shopmate_ecommerce_assistant.rag.policy_qa import CONFLICT_TEXT, REFUSAL_TEXT, AnswerModelError
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

    async def answer(self, question, scope, *, query_plan=None, generation=None):
        raise self._exc


def _success(data: dict[str, Any], *, as_of: datetime | None = None) -> ToolSuccess:
    return ToolSuccess(
        tool_call_id=uuid4(),
        data=data,
        as_of=as_of or datetime.now(UTC),
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


class RoutingDispatcher:
    """Returns one canned result **per tool name** and records the call order.

    ``FakeDispatcher`` answers every tool with the same envelope, which cannot express
    "search resolves the name, then ``get_product_detail`` produces the facts".
    """

    def __init__(self, results: dict[str, ToolSuccess | ToolFailure]) -> None:
        self._results = results
        self.calls: list[str] = []

    async def invoke(self, tool_name: str, payload: Any, *, context: ToolContext):
        self.calls.append(tool_name)
        if tool_name not in self._results:
            raise AssertionError(f"unexpected tool: {tool_name}")
        return self._results[tool_name]


class FixedPolicy:
    """Returns a canned ``PolicyAnswer``-shaped object; ``status`` is what matters here."""

    def __init__(self, *, status: str, answer_text: str, citations: tuple = ()) -> None:
        self._status = status
        self._answer_text = answer_text
        self._citations = citations
        self.generations: list[object] = []

    async def answer(self, question, scope, *, query_plan=None, generation=None):
        self.generations.append(generation)
        return SimpleNamespace(
            status=self._status, answer_text=self._answer_text, citations=self._citations
        )


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


def _citation() -> Citation:
    return Citation(
        citation_id="cit_0000000000000001",
        label="c1",
        document_id=uuid4(),
        chunk_id=uuid4(),
        version_id=uuid4(),
        title="退换货政策",
        heading="七天无理由退货",
        page_no=2,
        version="2026.10.1",
        effective_from="2026-10-01T00:00:00",
        effective_to=None,
        snippet="合成政策片段：自签收之日起七天内可申请无理由退货。",
        score=0.71,
        dense_similarity=0.71,
    )


@pytest.mark.parametrize(
    ("status", "answer_text", "expected"),
    [
        # A refusal used to be reported as finish_reason="stop", so the client never
        # showed 已拒答 (MessageBubble.vue keys off finish_reason === 'refusal').
        ("refused", REFUSAL_TEXT, "refusal"),
        ("handoff", CONFLICT_TEXT, "handoff"),
        ("answered", "七天无理由退货需保持商品完好 [c1]。", "stop"),
    ],
)
async def test_policy_answer_status_drives_the_reported_finish_reason(
    settings: Settings, status: str, answer_text: str, expected: str
) -> None:
    citations = (_citation(),) if status == "answered" else ()
    policy = FixedPolicy(status=status, answer_text=answer_text, citations=citations)
    service = _service(FakeDispatcher(_success({})), settings, policy=policy)
    route = _route("七天无理由退货的政策是什么？", settings)

    outcome = await service._run(route, "七天无理由退货的政策是什么？", _tool_context())

    assert outcome.finish_reason == expected



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


# -- stage 18: PRODUCT_FACT must use the contract tool, not the search list ----------
#
# docs/05-tool-contract.md §5.2/§5.4: price/spec answers come from ``get_product_detail``
# and availability from ``check_stock``. Before this fix every fact turn stopped at
# ``search_products`` (9 business cases, eval-033…037 and eval-130…133), so the answer was
# a recommendation list rather than the asked-for fact. The assertions below are the
# before/after contract: the first tool is still the lookup, the *second* tool is the one
# that actually answers, and "search only" must never be the whole call sequence again.

_AS_OF = datetime(2026, 10, 22, 7, 0, tzinfo=UTC)


def _search_item(
    *,
    product_id: str,
    variant_id: str,
    title: str,
    price_cents: int,
    available_qty: int | None,
    stock_status: str = "in_stock",
) -> dict[str, Any]:
    return {
        "product_id": product_id,
        "variant_id": variant_id,
        "title": title,
        "price_cents": price_cents,
        "currency": "CNY",
        "stock_status": stock_status,
        "available_qty": available_qty,
        "attributes": {},
        "matched_reasons": ["关键词"],
        "is_synthetic": True,
        "as_of": _AS_OF.isoformat(),
    }


_NC300 = _search_item(
    product_id="11111111-1111-1111-1111-111111111111",
    variant_id="21111111-1111-1111-1111-111111111111",
    title="声岚 SL-NC300 入耳式降噪耳机 · 云雾白",
    price_cents=29900,
    available_qty=7,
)
_BUDS_AIR = _search_item(
    product_id="12222222-2222-2222-2222-222222222222",
    variant_id="22222222-2222-2222-2222-222222222222",
    title="声岚 SL-BUDS Air 真无线蓝牙耳机 · 云雾白",
    price_cents=34900,
    available_qty=3,
)
_BUDS_LITE = _search_item(
    product_id="13333333-3333-3333-3333-333333333333",
    variant_id="23333333-3333-3333-3333-333333333333",
    title="声岚 SL-BUDS Lite 真无线耳机 · 碳黑",
    price_cents=19900,
    available_qty=0,
    stock_status="out_of_stock",
)
_BUDS_PRO = _search_item(
    product_id="16666666-6666-6666-6666-666666666666",
    variant_id="26666666-6666-6666-6666-666666666666",
    title="声岚 SL-BUDS Pro 真无线降噪耳机 · 深空灰",
    price_cents=49900,
    available_qty=4,
)
_KC87 = _search_item(
    product_id="14444444-4444-4444-4444-444444444444",
    variant_id="24444444-4444-4444-4444-444444444444",
    title="键川 KC87 三模机械键盘 · 深空灰",
    price_cents=45900,
    available_qty=12,
)
_KC104 = _search_item(
    product_id="15555555-5555-5555-5555-555555555555",
    variant_id="25555555-5555-5555-5555-555555555555",
    title="键川 KC104 全尺寸机械键盘 · 深空灰",
    price_cents=55900,
    available_qty=5,
)


def _detail_payload(item: dict[str, Any], *, brand: str = "声岚") -> dict[str, Any]:
    return {
        "product": {
            "id": item["product_id"],
            "title": item["title"].split(" · ")[0],
            "brand": brand,
            "category": "耳机",
            "attributes": {},
            "status": "active",
            "is_synthetic": True,
            "stock_summary": {
                "available_qty": item["available_qty"],
                "stock_status": item["stock_status"],
                "updated_at": _AS_OF.isoformat(),
            },
            "variants": [
                {
                    "id": item["variant_id"],
                    "sku": "DEMO-HEAD-001-WHT",
                    "title": "云雾白",
                    "attributes": {},
                    "price_cents": item["price_cents"],
                    "currency": "CNY",
                    "status": "active",
                    "available_qty": item["available_qty"],
                    "stock_status": item["stock_status"],
                    "stock_updated_at": _AS_OF.isoformat(),
                }
            ],
        }
    }


def _stock_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "variant_id": item["variant_id"],
        "product_id": item["product_id"],
        "sku": "DEMO-HEAD-001-WHT",
        "requested_qty": 1,
        "available_qty": item["available_qty"],
        "is_available": bool(item["available_qty"]),
        "stock_status": item["stock_status"],
        "warehouses": [
            {
                "warehouse_code": "DEMO-WH-01",
                "available_qty": item["available_qty"],
                "updated_at": _AS_OF.isoformat(),
            }
        ],
    }


@pytest.mark.parametrize(
    ("text", "items", "tool", "item", "needles"),
    [
        # eval-033 / 035 / 037: availability → check_stock
        (
            "声岚 SL-NC300 入耳式降噪耳机 现在还有货吗？",
            [_NC300, _BUDS_AIR],
            "check_stock",
            _NC300,
            ("声岚 SL-NC300", "有货", "7"),
        ),
        (
            "声岚 SL-BUDS Lite 真无线耳机 现在还有货吗？",
            [_BUDS_LITE, _BUDS_AIR],
            "check_stock",
            _BUDS_LITE,
            ("暂时无货",),
        ),
        (
            "键川 KC87 三模机械键盘 现在还有货吗？",
            [_KC87, _KC104],
            "check_stock",
            _KC87,
            ("键川 KC87", "12"),
        ),
        # eval-034 / 036: price/spec → get_product_detail
        (
            "声岚 SL-BUDS Air 真无线蓝牙耳机 卖多少钱？",
            [_BUDS_AIR, _BUDS_LITE],
            "get_product_detail",
            _BUDS_AIR,
            ("声岚 SL-BUDS Air", "¥349"),
        ),
        (
            "声岚 SL-BUDS Pro 真无线降噪耳机 卖多少钱？",
            [_BUDS_LITE, _BUDS_PRO],
            "get_product_detail",
            _BUDS_PRO,
            ("声岚 SL-BUDS Pro", "¥499"),
        ),
        # eval-130…133: a bare category still resolves to one item, and says so
        (
            "机械键盘多少钱？",
            [_KC87, _KC104],
            "get_product_detail",
            _KC87,
            ("供你参考", "¥459"),
        ),
        (
            "蓝牙音箱还有货吗？",
            [_NC300],
            "check_stock",
            _NC300,
            ("有货",),
        ),
        (
            "智能手表续航多久？",
            [_KC87],
            "get_product_detail",
            _KC87,
            ("¥459",),
        ),
        (
            "充电器支持快充吗？",
            [_BUDS_AIR],
            "get_product_detail",
            _BUDS_AIR,
            ("¥349",),
        ),
    ],
)
async def test_product_fact_answers_with_the_contract_tool(
    settings: Settings,
    text: str,
    items: list[dict[str, Any]],
    tool: str,
    item: dict[str, Any],
    needles: tuple[str, ...],
) -> None:
    payload = _detail_payload(item) if tool == "get_product_detail" else _stock_payload(item)
    dispatcher = RoutingDispatcher(
        {
            "search_products": _success({"items": items}),
            tool: _success(payload, as_of=_AS_OF),
        }
    )
    service = _service(dispatcher, settings)
    route = _route(text, settings)
    assert route.intent is Intent.PRODUCT_FACT, route.as_dict()

    outcome = await service._run(route, text, _tool_context())

    # The lookup is allowed; stopping there is exactly the defect this test pins.
    assert dispatcher.calls == ["search_products", tool], dispatcher.calls
    for needle in needles:
        assert needle in outcome.answer_text, outcome.answer_text
    assert "数据更新时间" in outcome.answer_text
    assert outcome.structured_facts_verified is True


async def test_product_fact_without_a_resolvable_item_keeps_the_card_list(
    settings: Settings,
) -> None:
    """No confident id → the stage-8 list answer, never a guessed product."""
    dispatcher = RoutingDispatcher({"search_products": _success({"items": [_NC300]})})
    service = _service(dispatcher, settings)
    text = "这个多少钱？"

    outcome = await service._run(_route(text, settings), text, _tool_context())

    assert dispatcher.calls == ["search_products"]
    assert "声岚 SL-NC300" in outcome.answer_text
    assert len(outcome.product_cards) == 1


# -- stage 18: comparison operands are names, not UUIDs ------------------------------
#
# docs/05-tool-contract.md §5.3: ``compare_products`` takes 2-4 product ids. Before this
# fix the chat path only recognised ids written in the message, so all 12 comparison
# business cases (eval-023…032, 134, 136) degraded to a clarification. The fix resolves
# each operand through the catalogue first; when an operand does not resolve, the old
# clarification is still the answer (asserted below). A category operand is represented
# by its best title overlap, because both keyboard operands expand to one family and the
# search can rank the same product first for both sides.


def _pid(n: int) -> str:
    """Deterministic UUID-shaped id for the fake catalogue."""
    return f"00000000-0000-4000-8000-{n:012d}"


def _catalog_item(n: int, title: str, price_cents: int = 29900) -> dict[str, Any]:
    """A ``search_products`` item (only the fields resolution/cards read)."""
    return {
        "product_id": _pid(n),
        "variant_id": _pid(n + 500),
        "title": title,
        "price_cents": price_cents,
        "currency": "CNY",
        "stock_status": "in_stock",
        "available_qty": 5,
        "attributes": {},
        "matched_reasons": [],
        "is_synthetic": True,
        "as_of": _AS_OF.isoformat(),
    }


_CATALOG: tuple[dict[str, Any], ...] = (
    _catalog_item(1, "声岚 SL-NC700 头戴式主动降噪耳机 · 深空灰"),
    _catalog_item(2, "声岚 SL-NC500 轻量头戴降噪耳机 · 雾银白"),
    _catalog_item(3, "声岚 SL-NC300 入耳式降噪耳机 · 云雾白"),
    _catalog_item(4, "声岚 SL-BUDS Air 真无线蓝牙耳机 · 云雾白"),
    _catalog_item(5, "声岚 SL-BUDS Lite 真无线耳机 · 碳黑"),
    _catalog_item(6, "声岚 SL-BUDS Pro 真无线降噪耳机 · 深空灰"),
    _catalog_item(7, "键川 KC87 三模机械键盘 · 深空灰"),
    _catalog_item(8, "键川 KC104 全尺寸机械键盘 · 深空灰"),
    _catalog_item(9, "键川 KC68 便携机械键盘 · 云雾白"),
    _catalog_item(10, "光影 GM-X1 无线鼠标 · 碳黑"),
    _catalog_item(11, "光影 GM-X2 人体工学无线鼠标 · 深空灰"),
    _catalog_item(12, "光影 GM-Lite 无线鼠标 · 云雾白"),
    _catalog_item(13, "速派 PD65 氮化镓充电器"),
    _catalog_item(14, "速派 PD100 氮化镓充电器"),
    _catalog_item(15, "速派 QC30 快充充电器"),
    _catalog_item(17, "键川 KW200 无线薄膜键盘 · 雾银白"),
    _catalog_item(20, "速派 PB10000 移动电源 · 云雾白"),
    _catalog_item(21, "速派 PB20000 移动电源 · 深空灰"),
)

_TITLES: dict[str, str] = {item["product_id"]: item["title"] for item in _CATALOG}


def _compare_payload(ids: list[str]) -> dict[str, Any]:
    return {
        "products": [
            {"product_id": pid, "title": _TITLES[pid], "variant_id": None} for pid in ids
        ],
        "rows": [
            {
                "key": "price",
                "label": "价格",
                "values": [
                    {
                        "product_id": pid,
                        "known": True,
                        "value": 29900,
                        "unit": "CNY_cents",
                        "display": "¥299",
                    }
                    for pid in ids
                ],
            }
        ],
    }


class CatalogDispatcher:
    """Searches a fixed catalogue; ``overrides`` narrow it for one operand.

    ``exact_overrides`` keys on the whole expanded query, which the keyboard
    operands need: "无线键盘" and "机械键盘" expand to overlapping strings, so a
    substring key cannot tell the two searches apart.
    """

    def __init__(
        self,
        *,
        compare: ToolSuccess,
        overrides: dict[str, list[dict[str, Any]]] | None = None,
        exact_overrides: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._compare = compare
        self._overrides = overrides or {}
        self._exact_overrides = exact_overrides or {}
        self.calls: list[tuple[str, str | None]] = []

    async def invoke(self, tool_name: str, payload: Any, *, context: ToolContext):
        if tool_name == "search_products":
            self.calls.append(("search_products", payload.query))
            if payload.query in self._exact_overrides:
                return _success({"items": self._exact_overrides[payload.query]})
            for key, items in self._overrides.items():
                if key in payload.query:
                    return _success({"items": items})
            return _success({"items": list(_CATALOG)})
        if tool_name == "compare_products":
            self.calls.append(("compare_products", None))
            return self._compare
        raise AssertionError(f"unexpected tool: {tool_name}")


@pytest.mark.parametrize(
    ("text", "expected_keys"),
    [
        # eval-023…032: model names on both sides
        ("声岚 SL-NC700 头戴式主动降噪耳机 和 声岚 SL-NC500 轻量头戴降噪耳机 有什么区别？", [1, 2]),
        ("声岚 SL-NC500 轻量头戴降噪耳机 和 声岚 SL-NC300 入耳式降噪耳机 有什么区别？", [2, 3]),
        ("声岚 SL-BUDS Air 真无线蓝牙耳机 和 声岚 SL-BUDS Lite 真无线耳机 有什么区别？", [4, 5]),
        ("声岚 SL-BUDS Lite 真无线耳机 和 声岚 SL-BUDS Pro 真无线降噪耳机 有什么区别？", [5, 6]),
        ("键川 KC87 三模机械键盘 和 键川 KC104 全尺寸机械键盘 有什么区别？", [7, 8]),
        ("键川 KC104 全尺寸机械键盘 和 键川 KC68 便携机械键盘 有什么区别？", [8, 9]),
        ("光影 GM-X1 无线鼠标 和 光影 GM-X2 人体工学无线鼠标 有什么区别？", [10, 11]),
        ("光影 GM-X2 人体工学无线鼠标 和 光影 GM-Lite 无线鼠标 有什么区别？", [11, 12]),
        ("速派 PD65 氮化镓充电器 和 速派 PD100 氮化镓充电器 有什么区别？", [13, 14]),
        ("速派 PD100 氮化镓充电器 和 速派 QC30 快充充电器 有什么区别？", [14, 15]),
    ],
)
async def test_compare_resolves_product_names_to_ids(
    settings: Settings, text: str, expected_keys: list[int]
) -> None:
    expected = [_pid(key) for key in expected_keys]
    dispatcher = CatalogDispatcher(compare=_success(_compare_payload(expected)))
    service = _service(dispatcher, settings)
    route = _route(text, settings)
    assert route.intent is Intent.PRODUCT_COMPARE, route.as_dict()

    outcome = await service._run(route, text, _tool_context())

    # before the fix: no tool at all, and a clarification instead of a comparison
    assert [call[0] for call in dispatcher.calls] == [
        "search_products",
        "search_products",
        "compare_products",
    ], dispatcher.calls
    assert "对比" in outcome.answer_text
    for pid in expected:
        assert _TITLES[pid].split(" · ")[0] in outcome.answer_text, outcome.answer_text


@pytest.mark.parametrize(
    ("text", "overrides", "expected_keys"),
    [
        # eval-134: two categories, so each side compares its best match and says so
        (
            "移动电源和充电器哪个更值得买？",
            {
                "移动电源": [
                    _catalog_item(20, "速派 PB10000 移动电源 · 云雾白"),
                    _catalog_item(21, "速派 PB20000 移动电源 · 深空灰"),
                ],
                "充电器": [
                    _catalog_item(13, "速派 PD65 氮化镓充电器"),
                    _catalog_item(14, "速派 PD100 氮化镓充电器"),
                ],
            },
            [20, 13],
        ),
        # eval-136: two keyboard categories, one representative each
        (
            "无线键盘和机械键盘有什么区别？",
            {
                "无线键盘": [_catalog_item(7, "键川 KC87 三模机械键盘 · 深空灰")],
                "机械键盘": [_catalog_item(8, "键川 KC104 全尺寸机械键盘 · 深空灰")],
            },
            [7, 8],
        ),
    ],
)
async def test_compare_of_two_categories_uses_one_representative_each(
    settings: Settings,
    text: str,
    overrides: dict[str, list[dict[str, Any]]],
    expected_keys: list[int],
) -> None:
    expected = [_pid(key) for key in expected_keys]
    dispatcher = CatalogDispatcher(
        compare=_success(_compare_payload(expected)), overrides=overrides
    )
    service = _service(dispatcher, settings)

    outcome = await service._run(_route(text, settings), text, _tool_context())

    assert [call[0] for call in dispatcher.calls] == [
        "search_products",
        "search_products",
        "compare_products",
    ], dispatcher.calls
    assert "对比" in outcome.answer_text


async def test_compare_keeps_the_distinguishing_word_when_hits_overlap(
    settings: Settings,
) -> None:
    """eval-136: both operands expand into the same keyboard family.

    The real catalogue ranks the membrane keyboard first for *both* "无线键盘"
    and "机械键盘" (its title carries 薄膜键盘, which both expansions contain), so
    a blind first hit made both sides resolve to one product and the dedup guard
    turned the turn back into a clarification. Each operand now keeps its own
    distinguishing word.
    """
    keyboards = [
        _catalog_item(17, "键川 KW200 无线薄膜键盘 · 雾银白"),
        _catalog_item(9, "键川 KC68 便携机械键盘 · 云雾白"),
        _catalog_item(7, "键川 KC87 三模机械键盘 · 深空灰"),
        _catalog_item(8, "键川 KC104 全尺寸机械键盘 · 深空灰"),
    ]
    expected = [_pid(17), _pid(9)]
    dispatcher = CatalogDispatcher(
        compare=_success(_compare_payload(expected)),
        exact_overrides={
            "无线键盘 机械键盘 薄膜键盘": keyboards,
            "机械键盘 薄膜键盘": keyboards,
        },
    )
    service = _service(dispatcher, settings)
    text = "无线键盘和机械键盘有什么区别？"

    outcome = await service._run(_route(text, settings), text, _tool_context())

    assert [call[0] for call in dispatcher.calls] == [
        "search_products",
        "search_products",
        "compare_products",
    ], dispatcher.calls
    assert "对比" in outcome.answer_text
    # the wireless side stays wireless, the mechanical side stays mechanical
    assert "键川 KW200 无线薄膜键盘" in outcome.answer_text
    assert "键川 KC68 便携机械键盘" in outcome.answer_text
    # a category comparison says it picked representatives
    assert "你没指定具体型号" in outcome.answer_text


@pytest.mark.parametrize(
    "text",
    [
        "这两款哪个好",  # no operands at all → keep the stage-8 clarification
        "声岚 SL-BUDS Air 和 完全不存在的型号 有什么区别？",  # one side unresolved
    ],
)
async def test_unresolvable_comparison_keeps_the_clarification(
    settings: Settings, text: str
) -> None:
    dispatcher = CatalogDispatcher(compare=_success(_compare_payload([_pid(4)])))
    service = _service(dispatcher, settings)
    route = _route(text, settings)
    assert route.intent is Intent.PRODUCT_COMPARE, route.as_dict()

    outcome = await service._run(route, text, _tool_context())

    assert "告诉我想要对比" in outcome.answer_text
    assert all(call[0] != "compare_products" for call in dispatcher.calls)


# -- stage 19: per-conversation generation parameters -------------------------


class _HistoryRepo:
    """Records the ``limit`` it was asked for and applies it like SQL ``LIMIT`` would."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows = rows or []
        self.limits: list[int] = []

    async def list_history(self, **kwargs: Any) -> list[Any]:
        limit = kwargs["limit"]
        self.limits.append(limit)
        return self.rows[:limit]


def _ctx():
    from shopmate_ecommerce_assistant.core.security import AccessContext
    from shopmate_ecommerce_assistant.db.models.enums import UserRole

    return AccessContext(
        shop_id=uuid4(), user_id=uuid4(), role=UserRole.SHOPPER, permissions=frozenset()
    )


def _message_row(role: str, content: str) -> Any:
    return SimpleNamespace(role=role, content=content)


async def test_recent_history_passes_the_configured_limit(settings: Settings) -> None:
    service = _service(FakeDispatcher(_success({})), settings)
    service._messages = _HistoryRepo([_message_row("user", "上一轮"), _message_row("user", "当轮")])
    ctx = _ctx()

    history = await service.recent_history(ctx, uuid4(), limit=4)

    assert history == ["上一轮", "当轮"]
    assert service._messages.limits == [4]


async def test_history_turns_zero_assembles_no_history(settings: Settings) -> None:
    """``history_turns=0`` must reach the query as ``LIMIT 0``, i.e. no history at all."""
    service = _service(FakeDispatcher(_success({})), settings)
    service._messages = _HistoryRepo([_message_row("user", "上一轮")])
    ctx = _ctx()

    assert await service.recent_history(ctx, uuid4(), limit=0) == []
    assert service._messages.limits == [0]


async def test_generation_params_reach_the_policy_service(settings: Settings) -> None:
    policy = FixedPolicy(status="answered", answer_text="可以退 [c1]。")
    service = _service(FakeDispatcher(_success({})), settings, policy=policy)
    route = _route("七天无理由怎么退", settings)
    generation = GenerationParams(temperature=0.7, history_turns=0)

    await service._run(route, "七天无理由怎么退", _tool_context(), generation=generation)

    assert policy.generations == [generation]


async def test_no_generation_keeps_the_pre_stage19_call(settings: Settings) -> None:
    policy = FixedPolicy(status="answered", answer_text="可以退 [c1]。")
    service = _service(FakeDispatcher(_success({})), settings, policy=policy)
    route = _route("七天无理由怎么退", settings)

    await service._run(route, "七天无理由怎么退", _tool_context())

    assert policy.generations == [None]


async def test_persona_prompt_carries_history_only_when_assembled(settings: Settings) -> None:
    """history_turns=0 must remove the persona context block entirely (stage 19)."""
    from shopmate_ecommerce_assistant.agents.persona import naturalize

    class _Model:
        name = "stub"

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def complete(self, *, system: str, user: str, generation=None) -> str:
            self.prompts.append(user)
            return "这条答复可以改写。"

    model = _Model()
    naturalize(
        "自签收之日起七日内可申请无理由退货。",
        user_text="那多久之内能退",
        settings=settings,
        model=model,
        history=["七天无理由怎么退"],
    )
    naturalize(
        "自签收之日起七日内可申请无理由退货。",
        user_text="那多久之内能退",
        settings=settings,
        model=model,
        history=[],
    )

    assert "最近的对话" in model.prompts[0]
    assert "七天无理由怎么退" in model.prompts[0]
    assert "最近的对话" not in model.prompts[1]


def test_sse_citation_payload_exposes_image_metadata() -> None:
    """An OCR'd passage must let the UI link the citation back to the screenshot."""
    from shopmate_ecommerce_assistant.agents.chat_service import _citation

    payload = _citation(
        {
            "citation_id": "cit_0000000000000002",
            "label": "c1",
            "document_id": "11111111-1111-1111-1111-111111111111",
            "chunk_id": "22222222-2222-2222-2222-222222222222",
            "version_id": "33333333-3333-3333-3333-333333333333",
            "title": "礼品卡使用说明（截图版）",
            "heading": "",
            "page_no": 1,
            "version": "2026.10.1",
            "effective_from": "2026-10-01T00:00:00",
            "effective_to": None,
            "snippet": "礼品卡自激活之日起三十六个月内有效。",
            "image_url": "/api/v1/knowledge-images/11111111-1111-1111-1111-111111111111",
            "image_filename": "gift-card-screenshot-2026.10.1.png",
            "image_width": 1080,
            "image_height": 1502,
        },
        as_of="2026-10-23T00:00:00Z",
    )

    assert payload["image_url"].endswith("/knowledge-images/11111111-1111-1111-1111-111111111111")
    assert payload["image_filename"] == "gift-card-screenshot-2026.10.1.png"
    assert payload["image_width"] == 1080
    assert payload["image_height"] == 1502
    assert payload["heading"] == ""
