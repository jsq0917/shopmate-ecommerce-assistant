"""Human handoff tool.

The model supplies only *why* it wants a human; the server supplies the risk level, the
full rule-code set and the priority. ``resolve_risk`` can therefore only raise the level,
never lower it, and a ticket is always created ``open`` — assignment and resolution belong
to the support desk.

The summary is PII-masked before it is stored, because it may quote user text.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from shopmate_ecommerce_assistant.core.errors import RETRYABLE_ERROR_CODES, ErrorCode, ToolError
from shopmate_ecommerce_assistant.domain.audit.models import AuditEventRecord, ToolCallRecord
from shopmate_ecommerce_assistant.domain.audit.ports import AuditSink, NullAuditSink
from shopmate_ecommerce_assistant.domain.handoff.ports import HandoffConflictError, HandoffWriter
from shopmate_ecommerce_assistant.domain.handoff.rules import resolve_risk
from shopmate_ecommerce_assistant.domain.idempotency import (
    OPERATION_CREATE_HANDOFF,
    ClaimKind,
    IdempotencyScope,
    IdempotencyState,
    IdempotencyStore,
)
from shopmate_ecommerce_assistant.domain.orders.ports import OrderReader
from shopmate_ecommerce_assistant.observability.metrics import handoff_total
from shopmate_ecommerce_assistant.safety.pii import mask_pii
from shopmate_ecommerce_assistant.safety.risk import RiskLevel
from shopmate_ecommerce_assistant.tools.audit import summarize_result
from shopmate_ecommerce_assistant.tools.context import ToolContext
from shopmate_ecommerce_assistant.tools.order_schemas import (
    MAX_HANDOFF_SUMMARY_CHARS,
    CreateHandoffTicketData,
    CreateHandoffTicketInput,
    validate_idempotency_key,
)
from shopmate_ecommerce_assistant.tools.runtime import ToolOutcome, ToolRuntime, utc_now
from shopmate_ecommerce_assistant.tools.schemas import ToolResult, ToolSuccess
from shopmate_ecommerce_assistant.tools.validation import validate_input

logger = logging.getLogger(__name__)

EXPECTED_RESPONSE = "客服将优先查看；这不是退款或赔偿承诺。"

MESSAGES: dict[str, str] = {
    "CONVERSATION_NOT_FOUND": "未找到可由当前账号访问的会话，无法创建人工工单。",
    "IDEMPOTENCY_CONFLICT": "本次请求与之前的请求不一致，请重新发起或查看原工单。",
    "IDEMPOTENCY_IN_PROGRESS": "相同的请求正在处理中，请稍后重试。",
    "VALIDATION_ERROR": "转人工请求参数不合法，请检查会话、原因或摘要。",
}

DEFAULT_MESSAGE = "人工工单创建失败，请稍后重试或联系客服。"


def message_for(code: str) -> str:
    """Return the stable Chinese message for a handoff error code."""
    return MESSAGES.get(code, DEFAULT_MESSAGE)


def request_hash(*, conversation_id: UUID, reason_code: str, summary: str) -> bytes:
    """Return the canonical digest of the business parameters for idempotency."""
    canonical = f"{conversation_id}|{reason_code}|{summary}"
    return hashlib.sha256(canonical.encode("utf-8")).digest()


class HandoffTools:
    """``create_handoff_ticket``."""

    def __init__(
        self,
        reader: OrderReader,
        *,
        store: IdempotencyStore,
        writer: HandoffWriter | None = None,
        audit: AuditSink | None = None,
        runtime: ToolRuntime | None = None,
        clock=utc_now,
    ) -> None:
        self._reader = reader
        self._store = store
        self._writer = writer
        self._audit: AuditSink = audit or NullAuditSink()
        self._runtime = runtime or ToolRuntime()
        self._clock = clock

    async def create_handoff_ticket(self, payload: object, *, context: ToolContext):
        """Create one ``open`` ticket; idempotent per key."""
        return await self._runtime.execute(
            "create_handoff_ticket",
            context=context,
            payload=payload,
            handler=self._create,
        )

    async def _create(self, payload: object, context: ToolContext) -> ToolOutcome:
        params = validate_input(CreateHandoffTicketInput, payload)
        context.ensure_conversation_read()
        now = self._clock()
        started = time.perf_counter()
        summary, _ = mask_pii(params.summary_redacted)
        summary = summary[:MAX_HANDOFF_SUMMARY_CHARS]

        # The key is server-injected (API header / server-side operation id), never model
        # payload, so the model cannot forge it (contract §5.10).
        try:
            key = validate_idempotency_key(context.idempotency_key)
        except ValueError as exc:
            raise ToolError(ErrorCode.VALIDATION_ERROR, message_for("VALIDATION_ERROR")) from exc

        scope = IdempotencyScope(
            shop_id=context.shop_id,
            actor_user_id=context.actor_user_id,
            operation=OPERATION_CREATE_HANDOFF,
            key=key,
        )
        digest = request_hash(
            conversation_id=params.conversation_id,
            reason_code=params.reason_code,
            summary=summary,
        )
        claim = await self._store.claim(scope, request_hash=digest)

        if claim.kind is ClaimKind.REPLAY:
            return await self._replay(claim.state, context, scope)
        if claim.kind is ClaimKind.CONFLICT:
            raise ToolError(ErrorCode.IDEMPOTENCY_CONFLICT, message_for("IDEMPOTENCY_CONFLICT"))
        if claim.kind is ClaimKind.IN_PROGRESS:
            raise ToolError(
                ErrorCode.IDEMPOTENCY_IN_PROGRESS,
                message_for("IDEMPOTENCY_IN_PROGRESS"),
                retryable=True,
                retry_after_ms=1500,
            )
        if claim.kind is ClaimKind.FAILED and claim.state is not None:
            code = claim.state.error_code or ErrorCode.VALIDATION_ERROR.value
            raise ToolError(_error_code(code), message_for(code))

        try:
            result = await self._submit(
                params,
                context,
                now=now,
                scope=scope,
                summary=summary,
                started=started,
            )
        except ToolError as exc:
            if exc.code.value in RETRYABLE_ERROR_CODES:
                await self._release(scope)
            else:
                await self._mark_failed(scope, exc.code.value)
            raise
        except Exception:
            # A transient failure must not poison the key forever: release the claim and
            # let the unique index keep duplicate creation impossible on retry.
            await self._release(scope)
            raise
        # Only freshly created tickets count (idempotent replays return above), so the
        # metric measures real escalations from every path — chat turns and the API.
        handoff_total.labels(params.reason_code).inc()
        return ToolOutcome(result, audit=False)

    async def _submit(
        self,
        params: CreateHandoffTicketInput,
        context: ToolContext,
        *,
        now: datetime,
        scope: IdempotencyScope,
        summary: str,
        started: float,
    ) -> ToolResult:
        conversation = await self._reader.get_conversation(
            shop_id=context.shop_id,
            conversation_id=params.conversation_id,
            user_id=context.subject_user_id,
        )
        if conversation is None:
            raise ToolError(ErrorCode.CONVERSATION_NOT_FOUND, message_for("CONVERSATION_NOT_FOUND"))

        risk_context = context.risk_context
        try:
            resolved = resolve_risk(
                params.reason_code,
                context_level=risk_context.level if risk_context else RiskLevel.LOW,
                context_codes=risk_context.codes if risk_context else (),
            )
        except ValueError as exc:
            raise ToolError(ErrorCode.VALIDATION_ERROR, message_for("VALIDATION_ERROR")) from exc

        if self._writer is None:
            raise ToolError(ErrorCode.INTERNAL_ERROR, DEFAULT_MESSAGE)

        ticket_id = uuid4()
        tool_call_id = uuid4()
        data = CreateHandoffTicketData(
            ticket_id=ticket_id,
            status="open",
            risk_level=resolved.level.value,
            priority=resolved.priority,
            queue=resolved.queue,
            primary_reason_code=resolved.primary_reason_code,
            reason_codes=list(resolved.reason_codes),
            expected_response=EXPECTED_RESPONSE,
            created_at=now,
        )
        success = ToolSuccess(
            tool_call_id=tool_call_id,
            data=data.model_dump(mode="json"),
            as_of=now,
            trace_id=context.trace_id,
        )
        record = ToolCallRecord(
            id=tool_call_id,
            request_id=context.request_id,
            trace_id=context.trace_id,
            shop_id=context.shop_id,
            conversation_id=params.conversation_id,
            user_id=context.subject_user_id,
            actor_user_id=context.actor_user_id,
            tool_name="create_handoff_ticket",
            input_redacted={
                "conversation_id": str(params.conversation_id),
                "reason_code": params.reason_code,
                "summary_redacted": summary,
                "idempotency_key_digest": _digest(scope.key),
            },
            result_summary=summarize_result("create_handoff_ticket", success),
            status="succeeded",
            error_code=None,
            latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
            idempotency_key=scope.key,
        )
        event = AuditEventRecord(
            id=uuid4(),
            shop_id=context.shop_id,
            actor_user_id=context.actor_user_id,
            actor_role=context.role.value,
            action="handoff_ticket.create",
            resource_type="handoff_ticket",
            resource_id=ticket_id,
            request_id=context.request_id,
            trace_id=context.trace_id,
            outcome="success",
            risk_level=resolved.level.value,
            metadata={
                "primary_reason_code": resolved.primary_reason_code,
                "reason_codes": list(resolved.reason_codes),
                "priority": resolved.priority,
            },
        )

        try:
            row = await self._writer.create_open(
                ticket_id=ticket_id,
                shop_id=context.shop_id,
                conversation_id=conversation.id,
                user_id=context.subject_user_id,
                risk_level=resolved.level.value,
                primary_reason_code=resolved.primary_reason_code,
                reason_codes=resolved.reason_codes,
                summary_redacted=summary,
                priority=resolved.priority,
                tool_call=record,
                audit=event,
                scope=scope,
                response=success.model_dump(mode="json"),
            )
        except HandoffConflictError as exc:
            raise ToolError(
                ErrorCode.IDEMPOTENCY_CONFLICT, message_for("IDEMPOTENCY_CONFLICT")
            ) from exc
        return ToolSuccess(
            tool_call_id=tool_call_id,
            data=data.model_dump(mode="json"),
            as_of=row.created_at,
            trace_id=context.trace_id,
        )

    async def _replay(
        self, state: IdempotencyState | None, context: ToolContext, scope: IdempotencyScope
    ) -> ToolOutcome:
        snapshot = dict(state.response or {}) if state is not None else {}
        data = snapshot.get("data")
        raw_id = snapshot.get("tool_call_id")
        if not data or not raw_id:
            raise ToolError(ErrorCode.IDEMPOTENCY_CONFLICT, message_for("IDEMPOTENCY_CONFLICT"))
        try:
            tool_call_id = UUID(str(raw_id))
            as_of = datetime.fromisoformat(str(snapshot.get("as_of")))
        except (TypeError, ValueError) as exc:
            raise ToolError(
                ErrorCode.IDEMPOTENCY_CONFLICT, message_for("IDEMPOTENCY_CONFLICT")
            ) from exc

        await self._record_replay(
            context,
            resource_id=state.resource_id if state is not None else None,
            metadata={"idempotency_key_digest": _digest(scope.key)},
        )
        return ToolOutcome(
            ToolSuccess(
                tool_call_id=tool_call_id,
                data=data,
                as_of=as_of,
                trace_id=context.trace_id,
                idempotent_replay=True,
            ),
            audit=False,
        )

    async def _record_replay(
        self,
        context: ToolContext,
        *,
        resource_id: UUID | None,
        metadata: Mapping[str, Any],
    ) -> None:
        event = AuditEventRecord(
            id=uuid4(),
            shop_id=context.shop_id,
            actor_user_id=context.actor_user_id,
            actor_role=context.role.value,
            action="handoff_ticket.idempotent_replay",
            resource_type="handoff_ticket",
            resource_id=resource_id,
            request_id=context.request_id,
            trace_id=context.trace_id,
            outcome="success",
            metadata=dict(metadata),
        )
        try:
            await self._audit.record_event(event)
        except Exception:
            logger.warning("handoff replay audit write failed")

    async def _mark_failed(self, scope: IdempotencyScope, error_code: str) -> None:
        try:
            await self._store.mark_failed(scope, error_code=error_code)
        except Exception:
            logger.warning("idempotency failure could not be recorded")

    async def _release(self, scope: IdempotencyScope) -> None:
        """Release a retryable-failed claim so the same key can be claimed again.

        The failed ``tool_calls`` audit row is intentionally kept (``status=failed`` +
        ``error_code`` + ``latency_ms``): the audit record says "this attempt failed", while
        the released idempotency record says "this key may now be retried".
        """
        try:
            await self._store.release(scope)
        except Exception:
            logger.warning("idempotency claim could not be released")


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _error_code(code: str) -> ErrorCode:
    try:
        return ErrorCode(code)
    except ValueError:
        return ErrorCode.INTERNAL_ERROR


__all__ = ["EXPECTED_RESPONSE", "HandoffTools", "MESSAGES", "message_for", "request_hash"]
