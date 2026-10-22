"""Chat orchestration: input guard -> route -> tools/RAG -> output guard -> persist.

This is the deterministic, single-agent turn pipeline behind ``POST /chat/stream``. Identity
and tenant scope come from the authenticated :class:`AccessContext`, never from the message.
Every tool call runs through the :class:`ToolDispatcher` with a server-built
:class:`ToolContext`; the model (when one exists) can only choose *which* allowed tool to
call and its business arguments, never its own identity, risk level or confirmation.

Without an LLM planner, the service uses a deterministic mini-planner: the router's intent
plus extracted entities decide the single tool to call and its arguments. Intents whose
arguments cannot be extracted deterministically (e.g. a return needs an ``order_item_id``)
are answered with an honest clarification instead of guessing.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shopmate_ecommerce_assistant.agents.answer_composer import (
    compose_compare,
    compose_order_status,
    compose_product_discovery,
    compose_purchase_intro,
    compose_return_eligibility,
    compose_shipment,
    compose_smalltalk,
)
from shopmate_ecommerce_assistant.agents.persona import naturalize_async
from shopmate_ecommerce_assistant.agents.query_understanding import (
    category_terms,
    expand_query,
    extract_budget_cents,
    infer_return_reason,
    match_line,
)
from shopmate_ecommerce_assistant.agents.router import Intent, IntentRoute, route_intent
from shopmate_ecommerce_assistant.agents.sse import (
    StreamEvent,
    citation_event,
    delta_event,
    done_event,
    error_event,
    meta_event,
    product_card_event,
    tool_status_event,
)
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.security import AccessContext
from shopmate_ecommerce_assistant.db.models.enums import ReturnReasonCode
from shopmate_ecommerce_assistant.db.repositories.checkout import CheckoutRepository
from shopmate_ecommerce_assistant.db.repositories.conversations import (
    ConversationRepository,
    MessageRepository,
)
from shopmate_ecommerce_assistant.db.repositories.orders import OrderRepository
from shopmate_ecommerce_assistant.rag.policy_qa import AnswerModelError, PolicyQAService
from shopmate_ecommerce_assistant.rag.query_rewrite import plan_query
from shopmate_ecommerce_assistant.rag.retrieval import RetrievalError, RetrievalScope
from shopmate_ecommerce_assistant.safety.input_guard import guard_input
from shopmate_ecommerce_assistant.safety.output_guard import guard_output
from shopmate_ecommerce_assistant.tools.context import RiskContext, ToolContext
from shopmate_ecommerce_assistant.tools.dispatcher import ToolDispatcher
from shopmate_ecommerce_assistant.tools.order_schemas import (
    CheckReturnEligibilityInput,
    GetOrderStatusInput,
    GetShipmentInput,
)
from shopmate_ecommerce_assistant.tools.schemas import (
    CompareProductsInput,
    SearchProductsInput,
    ToolFailure,
    ToolSuccess,
)

logger = logging.getLogger(__name__)

DELTA_CHUNK_CHARS = 40
UPSTREAM_TEXT = "当前无法确认最新信息，请稍后重试或转人工协助。"
POLICY_UNAVAILABLE_TEXT = "当前知识库暂不可用，无法确认政策依据，请转人工客服核实。"
RETURN_CLARIFY_TEXT = "请告诉我订单中具体要退货的商品（名称或规格），我会继续为你核对退货资格。"
COMPARE_CLARIFY_TEXT = "请告诉我想要对比的 2–4 个具体商品（名称或链接），我再帮你横向比较。"
ORDER_CLARIFY_TEXT = "请提供订单号（例如 DEMO-1001），我帮你查询当前状态。"
SHIPMENT_CLARIFY_TEXT = "请提供订单号，我帮你查询物流进度。"


@dataclass(slots=True)
class ChatOutcome:
    """What the turn produced, ready to stream and persist."""

    answer_text: str
    pre_events: list[StreamEvent] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    #: ``[cN]`` labels the answer text may reference. Kept next to the citation payloads
    #: because the output guard validates labels, not citation ids.
    citation_labels: list[str] = field(default_factory=list)
    structured_facts_verified: bool = False
    risk: dict[str, Any] = field(default_factory=dict)
    #: 商品卡片，既要随 SSE 发出，也要随助手消息落库。
    product_cards: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"


def _chunk_text(text: str, size: int = DELTA_CHUNK_CHARS) -> list[str]:
    if not text:
        return [""]
    return [text[index : index + size] for index in range(0, len(text), size)]


class ChatService:
    """Turn pipeline; one instance per request (owns one database session)."""

    def __init__(
        self,
        *,
        session,
        settings: Settings,
        dispatcher: ToolDispatcher | None = None,
        policy: PolicyQAService | None = None,
        clock=None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._dispatcher = dispatcher or ToolDispatcher(session=session, settings=settings)
        self._policy = policy
        self._clock = clock or (lambda: datetime.now(UTC))
        self._conversations = ConversationRepository(session)
        self._messages = MessageRepository(session)

    # -- pre-flight (run before the stream is established) -----------------
    async def ensure_conversation(self, ctx: AccessContext, conversation_id: UUID) -> None:
        """Raise ``ToolError(CONVERSATION_NOT_FOUND)`` when the user does not own it."""
        row = await self._conversations.get(
            shop_id=ctx.shop_id, user_id=ctx.user_id, conversation_id=conversation_id
        )
        if row is None:
            raise ToolError(ErrorCode.CONVERSATION_NOT_FOUND, "未找到可由当前账号访问的会话。")

    async def insert_user_message(
        self, ctx: AccessContext, conversation_id: UUID, message: str, client_message_id: UUID
    ) -> UUID:
        """Insert the user message once (idempotent per ``client_message_id``)."""
        row = await self._messages.insert_user_message(
            shop_id=ctx.shop_id,
            conversation_id=conversation_id,
            user_id=ctx.user_id,
            content=message,
            client_message_id=client_message_id,
        )
        return row.id

    async def recent_history(self, ctx: AccessContext, conversation_id: UUID) -> list[str]:
        """Return recent user turns (oldest first) for routing/rewriting."""
        rows = await self._messages.list_history(
            shop_id=ctx.shop_id, conversation_id=conversation_id, user_id=ctx.user_id, limit=10
        )
        return [row.content for row in rows if row.role == "user"]

    # -- streaming ---------------------------------------------------------
    async def stream(
        self,
        *,
        ctx: AccessContext,
        conversation_id: UUID,
        message: str,
        request_id: UUID,
        trace_id: UUID,
        user_message_id: UUID,
    ) -> AsyncIterator[StreamEvent]:
        """Yield the SSE business events for one already-accepted user turn."""
        guard = guard_input(message, settings=self._settings)
        history = await self.recent_history(ctx, conversation_id)
        route = route_intent(
            guard.sanitized_text or message, history=history, settings=self._settings
        )

        yield meta_event(
            {
                "trace_id": str(trace_id),
                "conversation_id": str(conversation_id),
                "user_message_id": str(user_message_id),
                "route": route.intent.value,
                "data_classification": "synthetic",
                "is_synthetic": True,
                "stream_version": "1.0",
            }
        )

        tool_context = ToolContext(
            shop_id=ctx.shop_id,
            actor_user_id=ctx.user_id,
            role=ctx.role,
            request_id=request_id,
            trace_id=trace_id,
            permissions=ctx.permissions,
            conversation_id=conversation_id,
            risk_context=RiskContext(level=route.risk.level, codes=route.risk.codes),
            route_confidence=route.confidence,
            # Server-owned idempotency key for the write tools this turn may reach. It is
            # derived from the already-persisted user message id, so retrying the same
            # message cannot create a second handoff ticket, and the model never sees it.
            idempotency_key=f"chat-turn-{user_message_id}",
        )

        try:
            outcome = await self._run(
                route, guard.sanitized_text or message, tool_context, history=history
            )
            if route.intent is not Intent.POLICY_FAQ:
                persona = await naturalize_async(
                    outcome.answer_text,
                    user_text=guard.sanitized_text or message,
                    settings=self._settings,
                    history=history,
                )
                if persona.rewritten:
                    outcome.answer_text = persona.text
        except ToolError as exc:
            # The error text is persisted once as an incomplete assistant snapshot so the
            # history can show "未完成" after a reconnect (contract 7.9 / 7.10).
            message_id = await self._persist_assistant(
                ctx,
                conversation_id,
                content=exc.user_message,
                route=route.intent.value,
                finish_reason="error",
                citations=[],
                risk=route.risk.as_dict(),
                is_complete=False,
            )
            yield error_event(
                {
                    "error_code": exc.code.value,
                    "user_message": exc.user_message,
                    "retryable": exc.retryable,
                    "retry_after_ms": exc.retry_after_ms,
                    "partial_message_id": str(message_id),
                    "partial_persisted": True,
                }
            )
            return

        for event in outcome.pre_events:
            yield event

        guarded = guard_output(
            outcome.answer_text,
            intent=route.intent.value,
            citation_labels=outcome.citation_labels or None,
            structured_facts_verified=outcome.structured_facts_verified,
        )
        final_text = guarded.text
        finish_reason = outcome.finish_reason
        if guarded.handoff_required:
            finish_reason = "handoff"
        elif not guarded.allowed:
            finish_reason = "refusal"

        message_id = await self._persist_assistant(
            ctx,
            conversation_id,
            content=final_text,
            route=route.intent.value,
            finish_reason=finish_reason,
            citations=outcome.citations,
            risk={**route.risk.as_dict(), **guarded.as_dict()},
            cards=outcome.product_cards,
            is_complete=finish_reason != "cancelled",
        )

        for index, chunk in enumerate(_chunk_text(final_text)):
            yield delta_event({"message_id": str(message_id), "index": index, "text": chunk})

        yield done_event(
            {
                "message_id": str(message_id),
                "finish_reason": finish_reason,
                "usage": None,
                "latency_ms": None,
                "persisted": True,
                "message_is_complete": finish_reason != "cancelled",
            }
        )

    # -- execution ---------------------------------------------------------
    async def _run(
        self, route: IntentRoute, text: str, tctx: ToolContext, history: list[str] | None = None
    ) -> ChatOutcome:
        intent = route.intent
        if route.handoff_required or intent is Intent.COMPLAINT_HANDOFF:
            return await self._handoff_outcome(route, tctx)
        if intent is Intent.POLICY_FAQ:
            return await self._policy_outcome(route, text, tctx)
        if intent is Intent.PURCHASE:
            return await self._search_outcome(route, text, tctx, history=history, purchase=True)
        if intent in {Intent.PRODUCT_DISCOVERY, Intent.PRODUCT_FACT}:
            return await self._search_outcome(route, text, tctx, history=history)
        if intent is Intent.PRODUCT_COMPARE:
            return await self._compare_outcome(route, tctx)
        if intent is Intent.ORDER_STATUS:
            return await self._order_outcome(route, tctx)
        if intent is Intent.SHIPMENT:
            return await self._shipment_outcome(route, tctx)
        if intent in {Intent.RETURN_ELIGIBILITY, Intent.RETURN_REQUEST}:
            return await self._return_outcome(route, text, tctx)
        if intent is Intent.REFUND_STATUS:
            return await self._refund_outcome(route, tctx)
        return ChatOutcome(
            answer_text=compose_smalltalk(intent, route.clarification_text, text=text),
            structured_facts_verified=True,
            risk=route.risk.as_dict(),
        )

    async def _invoke(
        self,
        tool_name: str,
        payload: Any,
        tctx: ToolContext,
        display_message: str,
        events: list[StreamEvent],
    ) -> ToolSuccess | ToolFailure:
        """Run one tool with ``tool_status`` events; return its envelope."""
        events.append(
            tool_status_event(
                {
                    "tool_call_id": None,
                    "tool_name": tool_name,
                    "status": "started",
                    "display_message": display_message,
                    "latency_ms": None,
                    "error_code": None,
                }
            )
        )
        result = await self._dispatcher.invoke(tool_name, payload, context=tctx)
        common = {
            "tool_call_id": str(result.tool_call_id),
            "tool_name": tool_name,
            "display_message": display_message,
            "latency_ms": None,
        }
        if result.ok:
            events.append(tool_status_event({**common, "status": "succeeded", "error_code": None}))
        else:
            events.append(
                tool_status_event({**common, "status": "failed", "error_code": result.error_code})
            )
        return result

    async def _search_outcome(
        self,
        route: IntentRoute,
        text: str,
        tctx: ToolContext,
        *,
        history: list[str] | None = None,
        purchase: bool = False,
    ) -> ChatOutcome:
        events: list[StreamEvent] = []
        # A short follow-up ("那有没有便宜点的") carries no product words of its own; fold the
        # previous user turn in so the search still has a topic.
        query = text
        if history and len(text.strip()) < 12:
            # ``history`` already contains this turn, so the previous topic is the most
            # recent *different* user message.
            previous = next(
                (
                    turn.strip()
                    for turn in reversed(history)
                    if turn.strip() and turn.strip() != text.strip()
                ),
                "",
            )
            if previous:
                # Prefer the previous turn's catalog words over its whole sentence: a long
                # sentence would eat the 20-token budget and drop the actual product term.
                topic = category_terms(previous)
                query = f"{' '.join(topic)} {text}" if topic else f"{previous} {text}"
        payload = SearchProductsInput(
            query=expand_query(query),
            budget_max_cents=extract_budget_cents(text),
            limit=8,
        )
        logger.debug("search payload query=%r budget=%r", query, payload.budget_max_cents)
        result = await self._invoke("search_products", payload, tctx, "正在搜索商品", events)
        if isinstance(result, ToolFailure):
            raise _as_tool_error(result)
        items = (result.data or {}).get("items", []) or []
        cards: list[dict[str, Any]] = [_product_card(item) for item in items]
        # Keep the catalog on-topic: a scenario word ("通勤") can match a backpack's
        # description even though the shopper asked for headphones.
        if any(word in text for word in ("便宜", "实惠", "省钱", "低一点")):
            cards.sort(key=lambda card: int(card["price_cents"]))
        terms = category_terms(text)
        if terms:
            on_topic = [
                card for card in cards if any(term in card["title"] for term in terms)
            ]
            if on_topic:
                cards = on_topic
        for card in cards:
            events.append(product_card_event(card))
        if purchase:
            answer = compose_purchase_intro(cards)
        else:
            answer = compose_product_discovery(cards, question=text)
        return ChatOutcome(
            answer_text=answer,
            pre_events=events,
            structured_facts_verified=True,
            risk=route.risk.as_dict(),
            product_cards=cards,
        )

    async def _compare_outcome(self, route: IntentRoute, tctx: ToolContext) -> ChatOutcome:
        events: list[StreamEvent] = []
        product_ids = route.entities.product_ids
        if len(product_ids) < 2:
            return ChatOutcome(
                answer_text=COMPARE_CLARIFY_TEXT,
                structured_facts_verified=True,
                risk=route.risk.as_dict(),
            )
        payload = CompareProductsInput(product_ids=[UUID(pid) for pid in product_ids[:4]])
        result = await self._invoke("compare_products", payload, tctx, "正在对比商品", events)
        if isinstance(result, ToolFailure):
            raise _as_tool_error(result)
        return ChatOutcome(
            answer_text=compose_compare(result.data or {}),
            pre_events=events,
            structured_facts_verified=True,
            risk=route.risk.as_dict(),
        )

    async def _order_outcome(self, route: IntentRoute, tctx: ToolContext) -> ChatOutcome:
        events: list[StreamEvent] = []
        order_nos = route.entities.order_nos
        if not order_nos:
            return ChatOutcome(
                answer_text=ORDER_CLARIFY_TEXT,
                structured_facts_verified=True,
                risk=route.risk.as_dict(),
            )
        result = await self._invoke(
            "get_order_status",
            GetOrderStatusInput(order_no=order_nos[0]),
            tctx,
            "正在查询订单状态",
            events,
        )
        if isinstance(result, ToolFailure):
            raise _as_tool_error(result)
        return ChatOutcome(
            answer_text=compose_order_status(result.data or {}),
            pre_events=events,
            structured_facts_verified=True,
            risk=route.risk.as_dict(),
        )

    async def _shipment_outcome(self, route: IntentRoute, tctx: ToolContext) -> ChatOutcome:
        events: list[StreamEvent] = []
        order_nos = route.entities.order_nos
        if not order_nos:
            return ChatOutcome(
                answer_text=SHIPMENT_CLARIFY_TEXT,
                structured_facts_verified=True,
                risk=route.risk.as_dict(),
            )
        status = await self._invoke(
            "get_order_status",
            GetOrderStatusInput(order_no=order_nos[0]),
            tctx,
            "正在查询订单",
            events,
        )
        if isinstance(status, ToolFailure):
            raise _as_tool_error(status)
        order_id = (status.data or {}).get("order_id")
        if order_id is None:
            return ChatOutcome(
                answer_text=compose_order_status(status.data or {}),
                pre_events=events,
                structured_facts_verified=True,
                risk=route.risk.as_dict(),
            )
        shipment = await self._invoke(
            "get_shipment",
            GetShipmentInput(order_id=UUID(str(order_id))),
            tctx,
            "正在查询物流",
            events,
        )
        if isinstance(shipment, ToolFailure):
            if shipment.error_code == ErrorCode.SHIPMENT_NOT_FOUND.value:
                return ChatOutcome(
                    answer_text="该订单暂无可查看的物流记录。",
                    pre_events=events,
                    structured_facts_verified=True,
                    risk=route.risk.as_dict(),
                )
            raise _as_tool_error(shipment)
        return ChatOutcome(
            answer_text=compose_shipment(shipment.data or {}),
            pre_events=events,
            structured_facts_verified=True,
            risk=route.risk.as_dict(),
        )

    async def _return_outcome(
        self, route: IntentRoute, text: str, tctx: ToolContext
    ) -> ChatOutcome:
        events: list[StreamEvent] = []
        order_nos = route.entities.order_nos
        if not order_nos:
            return ChatOutcome(
                answer_text=(
                    "我可以帮你核对退货资格。把订单号发给我（例如 SM-2026-00101），"
                    "并说一句想退哪件商品就行。"
                ),
                structured_facts_verified=True,
                risk=route.risk.as_dict(),
            )
        status = await self._invoke(
            "get_order_status",
            GetOrderStatusInput(order_no=order_nos[0]),
            tctx,
            "正在查询订单",
            events,
        )
        if isinstance(status, ToolFailure):
            raise _as_tool_error(status)
        order_id = (status.data or {}).get("order_id")
        if order_id is None:
            return ChatOutcome(
                answer_text=compose_order_status(status.data or {}),
                pre_events=events,
                structured_facts_verified=True,
                risk=route.risk.as_dict(),
            )

        items = await OrderRepository(self._session).list_order_items(
            shop_id=tctx.shop_id, order_id=UUID(str(order_id))
        )
        if not items:
            return ChatOutcome(
                answer_text="这个订单里没有可退货的商品。你可以查看退货政策，或转人工核实。",
                pre_events=events,
                structured_facts_verified=True,
                risk=route.risk.as_dict(),
            )

        chosen = match_line(
            text, [(item.id, item.sku, item.title) for item in items]
        )
        if chosen is None:
            names = "、".join(f"「{item.title}」" for item in items[:4])
            more = "等" if len(items) > 4 else ""
            return ChatOutcome(
                answer_text=(
                    f"订单 {order_nos[0]} 里有 {names}{more}，你想退哪一件？"
                    "告诉我商品名或规格，我再帮你核对退货条件。"
                ),
                pre_events=events,
                structured_facts_verified=True,
                risk=route.risk.as_dict(),
            )

        reason = infer_return_reason(text) or ReturnReasonCode.NO_LONGER_NEEDED
        decision = await self._invoke(
            "check_return_eligibility",
            CheckReturnEligibilityInput(
                order_id=UUID(str(order_id)), order_item_id=chosen, reason_code=reason
            ),
            tctx,
            "正在核对退货条件",
            events,
        )
        if isinstance(decision, ToolFailure):
            return ChatOutcome(
                answer_text=decision.user_message,
                pre_events=events,
                structured_facts_verified=True,
                risk=route.risk.as_dict(),
            )
        return ChatOutcome(
            answer_text=compose_return_eligibility(decision.data or {}),
            pre_events=events,
            structured_facts_verified=True,
            risk=route.risk.as_dict(),
        )

    async def _refund_outcome(self, route: IntentRoute, tctx: ToolContext) -> ChatOutcome:
        """Report the caller's own refund applications (never shop-wide)."""
        rows = await CheckoutRepository(self._session).list_refunds(
            shop_id=tctx.shop_id, user_id=tctx.actor_user_id, limit=5
        )
        if not rows:
            return ChatOutcome(
                answer_text=(
                    "你目前还没有提交过退款申请。可以在「我的订单」里打开对应订单，"
                    "点「申请退款」提交；如果商品已经收到，也可以直接申请退货。"
                    "需要我帮你查某个订单的状态吗？"
                ),
                structured_facts_verified=True,
                risk=route.risk.as_dict(),
            )
        status_labels = {
            "requested": "等待客服审核",
            "approved": "已通过，退款处理中",
            "rejected": "未通过",
            "completed": "已完成",
        }
        lines = [f"我查到你有 {len(rows)} 笔退款申请："]
        for row in rows[:3]:
            amount = (
                row.amount_cents // 100
                if row.amount_cents % 100 == 0
                else row.amount_cents / 100
            )
            label = status_labels.get(row.status, row.status)
            lines.append(
                f"· {row.refund_no}：订单 {row.order_no}，¥{amount}，{label}"
                + (f"（{row.review_note}）" if row.review_note else "")
            )
        lines.append("退款审核通过后会原路退回，具体到账时间以银行或支付渠道为准。")
        return ChatOutcome(
            answer_text="\n".join(lines),
            structured_facts_verified=True,
            risk=route.risk.as_dict(),
        )

    async def _policy_outcome(
        self, route: IntentRoute, text: str, tctx: ToolContext
    ) -> ChatOutcome:
        events: list[StreamEvent] = []
        if self._policy is None:
            return ChatOutcome(
                answer_text=POLICY_UNAVAILABLE_TEXT,
                pre_events=events,
                structured_facts_verified=False,
                risk=route.risk.as_dict(),
            )
        scope = RetrievalScope(shop_id=str(tctx.shop_id))
        plan = plan_query(text, settings=self._settings, intent=route.intent.value)
        try:
            answer = await self._policy.answer(text, scope, query_plan=plan)
        except (AnswerModelError, RetrievalError):
            return ChatOutcome(
                answer_text=UPSTREAM_TEXT,
                pre_events=events,
                structured_facts_verified=False,
                risk=route.risk.as_dict(),
            )
        citations: list[dict[str, Any]] = []
        labels: list[str] = []
        as_of = self._clock().isoformat()
        for citation in answer.citations:
            payload = _citation(citation.as_dict(), as_of=as_of)
            citations.append(payload)
            labels.append(citation.label)
            events.append(citation_event(payload))
        return ChatOutcome(
            answer_text=answer.answer_text,
            pre_events=events,
            citations=citations,
            citation_labels=labels,
            structured_facts_verified=False,
            risk=route.risk.as_dict(),
        )

    async def _handoff_outcome(self, route: IntentRoute, tctx: ToolContext) -> ChatOutcome:
        events: list[StreamEvent] = []
        reason_code = route.risk.primary_reason_code or "USER_REQUESTS_HUMAN"
        summary = "系统检测到风险升级，需要人工跟进。" if route.risk.codes else "用户请求人工协助。"
        payload = {
            "conversation_id": str(tctx.conversation_id),
            "reason_code": reason_code,
            "summary_redacted": summary,
        }
        result = await self._invoke(
            "create_handoff_ticket", payload, tctx, "正在转接人工客服", events
        )
        if isinstance(result, ToolFailure):
            raise _as_tool_error(result)
        data = result.data or {}
        ticket_id = data.get("ticket_id", "")
        return ChatOutcome(
            answer_text=(
                f"已为你转接人工客服，工单号 {ticket_id}，客服将优先处理。这不是退款或赔偿承诺。"
            ),
            pre_events=events,
            structured_facts_verified=True,
            risk=route.risk.as_dict(),
            finish_reason="handoff",
        )

    # -- persistence -------------------------------------------------------
    async def _persist_assistant(
        self,
        ctx: AccessContext,
        conversation_id: UUID,
        *,
        content: str,
        route: str,
        finish_reason: str,
        citations: list[dict[str, Any]],
        risk: dict[str, Any],
        is_complete: bool,
        cards: list[dict[str, Any]] | None = None,
    ) -> UUID:
        row = await self._messages.insert_assistant_message(
            shop_id=ctx.shop_id,
            conversation_id=conversation_id,
            user_id=ctx.user_id,
            content=content,
            route=route,
            finish_reason=finish_reason,
            citations={"items": citations},
            risk=risk,
            cards=cards or [],
            is_complete=is_complete,
        )
        return row.id


def _as_tool_error(result: ToolFailure) -> ToolError:
    return ToolError(
        _to_error_code(result.error_code),
        result.user_message,
        retryable=result.retryable,
        retry_after_ms=result.retry_after_ms,
    )


def _to_error_code(code: str | None) -> ErrorCode:
    try:
        return ErrorCode(code or ErrorCode.INTERNAL_ERROR.value)
    except ValueError:
        return ErrorCode.INTERNAL_ERROR


def _product_card(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "product_id": item["product_id"],
        "variant_id": item["variant_id"],
        "title": item["title"],
        # Cards carry the category so the client can render a stable placeholder cover.
        "category": item.get("category"),
        "image_url": item.get("image_url"),
        "price_cents": item["price_cents"],
        "currency": item["currency"],
        "stock_status": item["stock_status"],
        "available_qty": item.get("available_qty"),
        "attributes": item.get("attributes") or {},
        "matched_reasons": item.get("matched_reasons") or [],
        "source": "postgres",
        "is_synthetic": item.get("is_synthetic", True),
        "as_of": item.get("as_of"),
    }


def _citation(citation: Mapping[str, Any], *, as_of: str | None = None) -> dict[str, Any]:
    """Build the SSE ``citation`` payload from a stage-7 citation.

    Ids are coerced to ``str``: a citation built straight from database metadata may carry
    ``UUID`` objects, and the SSE frame is serialized with the stdlib JSON encoder.
    """
    return {
        "citation_id": str(citation["citation_id"]),
        "label": citation.get("label"),
        "document_id": str(citation["document_id"]),
        "version_id": str(citation["version_id"]),
        "chunk_id": str(citation["chunk_id"]),
        "title": citation["title"],
        "heading": citation.get("heading"),
        "page_no": citation.get("page_no"),
        "version": citation["version"],
        "effective_from": citation.get("effective_from"),
        "effective_to": citation.get("effective_to"),
        "excerpt": citation.get("snippet"),
        # Retrieval time of this turn: the knowledge facts are only "as of" this moment.
        "as_of": as_of,
    }


__all__ = ["ChatOutcome", "ChatService", "DELTA_CHUNK_CHARS"]
