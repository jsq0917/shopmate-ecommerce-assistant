"""Deterministic return tools: eligibility check and application submission.

Two safety properties are structural rather than prompt-level:

* ``check_return_eligibility`` is read-only and returns a signed token only for an
  ``eligible`` decision;
* ``create_return_request`` refuses to write unless the token verifies, the server-side
  confirmation grant covers this exact item and reason, and the rules — re-evaluated
  inside the write path — still say eligible. It writes ``submitted`` only. No code path
  in this module can approve a refund, and the response says so explicitly.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from shopmate_ecommerce_assistant.core.errors import RETRYABLE_ERROR_CODES, ErrorCode, ToolError
from shopmate_ecommerce_assistant.db.models.enums import ReturnReasonCode
from shopmate_ecommerce_assistant.domain.audit.models import AuditEventRecord, ToolCallRecord
from shopmate_ecommerce_assistant.domain.audit.ports import AuditSink, NullAuditSink
from shopmate_ecommerce_assistant.domain.idempotency import (
    OPERATION_CREATE_RETURN,
    ClaimKind,
    IdempotencyScope,
    IdempotencyState,
    IdempotencyStore,
)
from shopmate_ecommerce_assistant.domain.orders.models import ActiveReturnSnapshot
from shopmate_ecommerce_assistant.domain.orders.ports import OrderReader
from shopmate_ecommerce_assistant.domain.returns.ports import (
    ReturnConflictError,
    ReturnWriter,
)
from shopmate_ecommerce_assistant.domain.returns.rules import (
    RULE_VERSION,
    ReturnCheck,
    ReturnEvaluation,
    evaluate_return,
    materials_for,
)
from shopmate_ecommerce_assistant.domain.returns.tokens import (
    MIN_SECRET_LENGTH,
    EligibilityClaims,
    EligibilityTokenError,
    issue_eligibility_token,
    verify_eligibility_token,
)
from shopmate_ecommerce_assistant.tools.audit import summarize_result
from shopmate_ecommerce_assistant.tools.context import ToolContext
from shopmate_ecommerce_assistant.tools.order_schemas import (
    CheckReturnEligibilityData,
    CheckReturnEligibilityInput,
    CreateReturnRequestData,
    CreateReturnRequestInput,
    ExistingReturnSummary,
    validate_idempotency_key,
)
from shopmate_ecommerce_assistant.tools.runtime import ToolOutcome, ToolRuntime, utc_now
from shopmate_ecommerce_assistant.tools.schemas import ToolResult, ToolSuccess
from shopmate_ecommerce_assistant.tools.validation import validate_input

logger = logging.getLogger(__name__)

RETURN_NOTICE = "申请已提交，但尚未退款；审核通过也不代表真实资金到账。"

MESSAGES: dict[str, str] = {
    "ORDER_NOT_FOUND": "未找到可由当前账号访问的订单或订单项。请核对订单号，或转人工协助。",
    "INVALID_STATE": "当前订单或商品状态不支持自助退货。请查看订单状态，或转人工协助。",
    "RETURN_NOT_ALLOWED": "该订单或商品不支持自助退货。可查看退货政策，或转人工协助。",
    "RETURN_WINDOW_EXPIRED": "已超过签收后 7 天的退货窗口，无法自助提交。可转人工申诉。",
    "DUPLICATE_RETURN": "该商品已有进行中的退货申请，不能重复提交。可查看原申请进度。",
    "MANUAL_REVIEW_REQUIRED": (
        "该退货需要人工核实商品或原因，暂不能自助提交。已为你准备转人工入口。"
    ),
    "LOW_CONFIDENCE": "暂无法确认退货原因。请补充说明商品问题，或转人工协助。",
    "CONFIRMATION_REQUIRED": "提交退货申请前需要你明确确认。请确认后再次提交。",
    "ELIGIBILITY_EXPIRED": "退货资格已过期或与当前订单不符，请重新检查退货资格。",
    "IDEMPOTENCY_CONFLICT": "本次请求与之前的请求不一致，请重新发起或查看原申请。",
    "IDEMPOTENCY_IN_PROGRESS": "相同的请求正在处理中，请稍后重试。",
    "FORBIDDEN": "当前账号无权执行该操作。请使用本人账号，或转人工协助。",
}

DEFAULT_MESSAGE = "本次退货申请未能提交，请稍后重试或转人工协助。"


def message_for(code: str) -> str:
    """Return the stable Chinese message for a decision/error code."""
    return MESSAGES.get(code, DEFAULT_MESSAGE)


def request_hash(*, order_id: UUID, order_item_id: UUID, reason_code: ReturnReasonCode) -> bytes:
    """Return the canonical business-parameter digest used by the idempotency scope."""
    canonical = f"{order_id}|{order_item_id}|{reason_code.value}"
    return hashlib.sha256(canonical.encode("utf-8")).digest()


class ReturnTools:
    """``check_return_eligibility`` and ``create_return_request``."""

    def __init__(
        self,
        reader: OrderReader,
        *,
        store: IdempotencyStore,
        writer: ReturnWriter | None = None,
        token_secret: str,
        token_ttl_seconds: int = 600,
        low_confidence_threshold: float = 0.70,
        audit: AuditSink | None = None,
        runtime: ToolRuntime | None = None,
        clock=utc_now,
    ) -> None:
        self._reader = reader
        self._store = store
        self._writer = writer
        self._token_secret = token_secret
        if len(token_secret) < MIN_SECRET_LENGTH:
            raise ValueError("退货资格令牌密钥强度不足")
        self._token_ttl = timedelta(seconds=token_ttl_seconds)
        self._low_confidence_threshold = low_confidence_threshold
        self._audit: AuditSink = audit or NullAuditSink()
        self._runtime = runtime or ToolRuntime()
        self._clock = clock

    async def check_return_eligibility(self, payload: object, *, context: ToolContext):
        """Return the deterministic decision, the deadline and (if eligible) a token."""
        return await self._runtime.execute(
            "check_return_eligibility",
            context=context,
            payload=payload,
            handler=self._check,
        )

    async def _check(self, payload: object, context: ToolContext) -> ToolOutcome:
        params = validate_input(CheckReturnEligibilityInput, payload)
        context.ensure_order_read()
        now = self._clock()

        order = await self._reader.get_order(
            shop_id=context.shop_id,
            user_id=context.subject_user_id,
            order_id=params.order_id,
        )
        item = (
            None
            if order is None
            else await self._reader.get_order_item(
                shop_id=context.shop_id,
                order_id=order.id,
                order_item_id=params.order_item_id,
            )
        )
        if order is None or item is None:
            data = _not_found_data(params.reason_code, now)
            return ToolOutcome(
                ToolSuccess(
                    tool_call_id=uuid4(),
                    data=data.model_dump(mode="json"),
                    as_of=now,
                    trace_id=context.trace_id,
                )
            )

        blocking_return = await self._reader.find_active_return(
            shop_id=context.shop_id, order_item_id=item.id
        )
        evaluation = evaluate_return(
            ReturnCheck(
                order_status=order.status,
                item_status=item.status,
                is_returnable=item.is_returnable,
                item_delivered_at=item.delivered_at,
                line_total_cents=item.line_total_cents,
                reason_code=params.reason_code,
                has_active_return=blocking_return is not None,
                now=now,
                confidence=context.route_confidence,
                clarification_attempted=context.clarification_attempted,
                low_confidence_threshold=self._low_confidence_threshold,
            )
        )

        token: str | None = None
        expires_at: datetime | None = None
        if evaluation.eligible:
            expires_at = now + self._token_ttl
            token = issue_eligibility_token(
                EligibilityClaims(
                    shop_id=context.shop_id,
                    user_id=context.subject_user_id,
                    order_id=order.id,
                    order_item_id=item.id,
                    reason_code=params.reason_code.value,
                    rule_version=RULE_VERSION,
                    decision="eligible",
                    issued_at=now,
                    expires_at=expires_at,
                    conversation_id=context.conversation_id,
                ),
                secret=self._token_secret,
            )

        data = _eligibility_data(
            evaluation,
            now=now,
            token=token,
            expires_at=expires_at,
            blocking_return=blocking_return,
        )
        return ToolOutcome(
            ToolSuccess(
                tool_call_id=uuid4(),
                data=data.model_dump(mode="json"),
                as_of=now,
                trace_id=context.trace_id,
            )
        )

    async def create_return_request(self, payload: object, *, context: ToolContext):
        """Create one ``submitted`` application; idempotent and never a refund."""
        return await self._runtime.execute(
            "create_return_request",
            context=context,
            payload=payload,
            handler=self._create,
        )

    async def _create(self, payload: object, context: ToolContext) -> ToolOutcome:
        params = validate_input(CreateReturnRequestInput, payload)
        context.ensure_return_write()
        now = self._clock()
        started = time.perf_counter()

        # The key is server-injected (API header / server-side operation id), never model
        # payload, so the model cannot forge it (contract §5.9).
        try:
            key = validate_idempotency_key(context.idempotency_key)
        except ValueError as exc:
            raise ToolError(ErrorCode.VALIDATION_ERROR, message_for("VALIDATION_ERROR")) from exc

        scope = IdempotencyScope(
            shop_id=context.shop_id,
            actor_user_id=context.actor_user_id,
            operation=OPERATION_CREATE_RETURN,
            key=key,
        )
        digest = request_hash(
            order_id=params.order_id,
            order_item_id=params.order_item_id,
            reason_code=params.reason_code,
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
            code = claim.state.error_code or ErrorCode.INVALID_STATE.value
            raise ToolError(_error_code(code), message_for(code))

        try:
            result = await self._submit(params, context, now=now, scope=scope, started=started)
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
        return ToolOutcome(result, audit=False)

    async def _submit(
        self,
        params: CreateReturnRequestInput,
        context: ToolContext,
        *,
        now: datetime,
        scope: IdempotencyScope,
        started: float,
    ) -> ToolResult:
        grant = context.confirmation
        if grant is None or not grant.covers(
            operation=OPERATION_CREATE_RETURN,
            now=now,
            order_id=params.order_id,
            order_item_id=params.order_item_id,
            reason_code=params.reason_code.value,
        ):
            raise ToolError(ErrorCode.CONFIRMATION_REQUIRED, message_for("CONFIRMATION_REQUIRED"))

        try:
            verify_eligibility_token(
                params.eligibility_token,
                secret=self._token_secret,
                shop_id=context.shop_id,
                user_id=context.subject_user_id,
                order_id=params.order_id,
                order_item_id=params.order_item_id,
                reason_code=params.reason_code.value,
                now=now,
            )
        except EligibilityTokenError as exc:
            raise ToolError(
                ErrorCode.ELIGIBILITY_EXPIRED, message_for("ELIGIBILITY_EXPIRED")
            ) from exc

        # Re-read inside the write path: the order may have changed between check and write.
        order = await self._reader.get_order(
            shop_id=context.shop_id,
            user_id=context.subject_user_id,
            order_id=params.order_id,
        )
        if order is None:
            raise ToolError(ErrorCode.ORDER_NOT_FOUND, message_for("ORDER_NOT_FOUND"))
        item = await self._reader.get_order_item(
            shop_id=context.shop_id, order_id=order.id, order_item_id=params.order_item_id
        )
        if item is None:
            raise ToolError(ErrorCode.ORDER_NOT_FOUND, message_for("ORDER_NOT_FOUND"))

        blocking_return = await self._reader.find_active_return(
            shop_id=context.shop_id, order_item_id=item.id
        )
        evaluation = evaluate_return(
            ReturnCheck(
                order_status=order.status,
                item_status=item.status,
                is_returnable=item.is_returnable,
                item_delivered_at=item.delivered_at,
                line_total_cents=item.line_total_cents,
                reason_code=params.reason_code,
                has_active_return=blocking_return is not None,
                now=now,
            )
        )
        if not evaluation.eligible:
            raise ToolError(
                _error_code(evaluation.decision_code),
                message_for(evaluation.decision_code),
            )

        if self._writer is None:
            raise ToolError(ErrorCode.INTERNAL_ERROR, DEFAULT_MESSAGE)

        return_id = uuid4()
        tool_call_id = uuid4()
        data = CreateReturnRequestData(
            return_request_id=return_id,
            status="submitted",
            submitted_at=now,
            review_required=True,
            required_materials=list(evaluation.required_materials),
            next_action="wait_for_review",
            refund_status="not_created",
            notice=RETURN_NOTICE,
        )
        success = ToolSuccess(
            tool_call_id=tool_call_id,
            data=data.model_dump(mode="json"),
            as_of=now,
            trace_id=context.trace_id,
        )
        record = self._tool_call_record(
            context=context,
            payload=params,
            result=success,
            latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
            tool_call_id=tool_call_id,
            idempotency_key=scope.key,
        )
        event = AuditEventRecord(
            id=uuid4(),
            shop_id=context.shop_id,
            actor_user_id=context.actor_user_id,
            actor_role=context.role.value,
            action="return_request.submit",
            resource_type="return_request",
            resource_id=return_id,
            request_id=context.request_id,
            trace_id=context.trace_id,
            outcome="success",
            metadata={
                "reason_code": params.reason_code.value,
                "rule_version": RULE_VERSION,
                "refund_status": "not_created",
            },
        )

        try:
            row = await self._writer.create_submitted(
                return_request_id=return_id,
                shop_id=context.shop_id,
                user_id=context.subject_user_id,
                order_id=order.id,
                order_item_id=item.id,
                reason_code=params.reason_code.value,
                required_materials=evaluation.required_materials,
                tool_call=record,
                audit=event,
                scope=scope,
                response=success.model_dump(mode="json"),
            )
        except ReturnConflictError as exc:
            raise ToolError(ErrorCode.DUPLICATE_RETURN, message_for("DUPLICATE_RETURN")) from exc

        # The writer committed the row; the response must describe what was persisted.
        return ToolSuccess(
            tool_call_id=tool_call_id,
            data=data.model_dump(mode="json"),
            as_of=row.submitted_at,
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
            action="return_request.idempotent_replay",
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
        action: str,
        resource_id: UUID | None,
        metadata: Mapping[str, Any],
    ) -> None:
        event = AuditEventRecord(
            id=uuid4(),
            shop_id=context.shop_id,
            actor_user_id=context.actor_user_id,
            actor_role=context.role.value,
            action=action,
            resource_type="return_request",
            resource_id=resource_id,
            request_id=context.request_id,
            trace_id=context.trace_id,
            outcome="success",
            metadata=dict(metadata),
        )
        try:
            await self._audit.record_event(event)
        except Exception:
            logger.warning("idempotent replay audit write failed")

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

    @staticmethod
    def _tool_call_record(
        *,
        context: ToolContext,
        payload: CreateReturnRequestInput,
        result: ToolResult,
        latency_ms: int,
        tool_call_id: UUID,
        idempotency_key: str,
    ) -> ToolCallRecord:
        return ToolCallRecord(
            id=tool_call_id,
            request_id=context.request_id,
            trace_id=context.trace_id,
            shop_id=context.shop_id,
            conversation_id=context.conversation_id,
            user_id=context.subject_user_id,
            actor_user_id=context.actor_user_id,
            tool_name="create_return_request",
            input_redacted={
                "order_id": str(payload.order_id),
                "order_item_id": str(payload.order_item_id),
                "reason_code": payload.reason_code.value,
                "idempotency_key_digest": _digest(idempotency_key),
            },
            result_summary=summarize_result("create_return_request", result),
            status="succeeded",
            error_code=None,
            latency_ms=latency_ms,
            idempotency_key=idempotency_key,
        )


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _error_code(code: str) -> ErrorCode:
    try:
        return ErrorCode(code)
    except ValueError:
        return ErrorCode.INTERNAL_ERROR


def _eligibility_data(
    evaluation: ReturnEvaluation,
    *,
    now: datetime,
    token: str | None,
    expires_at: datetime | None,
    blocking_return: ActiveReturnSnapshot | None,
) -> CheckReturnEligibilityData:
    return CheckReturnEligibilityData(
        decision=evaluation.decision.value,
        decision_code=evaluation.decision_code,
        error_code=None if evaluation.eligible else evaluation.decision_code,
        eligible=evaluation.eligible,
        needs_clarification=evaluation.needs_clarification,
        needs_manual_review=evaluation.needs_manual_review,
        can_create_return_request=evaluation.can_create_return_request,
        handoff_required=evaluation.handoff_required,
        matched_rule_codes=list(evaluation.matched_rule_codes),
        deadline_at=evaluation.deadline_at,
        rule_version=RULE_VERSION,
        required_materials=list(evaluation.required_materials),
        next_action=evaluation.next_action,
        eligibility_token=token,
        eligibility_expires_at=expires_at,
        evaluated_at=now,
        handoff_reason_code=evaluation.handoff_reason_code,
        existing_return=(
            None
            if blocking_return is None
            else ExistingReturnSummary(
                return_request_id=blocking_return.id,
                status=blocking_return.status.value,
                reason_code=blocking_return.reason_code,
                requested_at=blocking_return.requested_at,
            )
        ),
    )


def _not_found_data(reason_code: ReturnReasonCode, now: datetime) -> CheckReturnEligibilityData:
    """A missing/foreign order is a business refusal, not an error envelope."""
    return CheckReturnEligibilityData(
        decision="ineligible",
        decision_code=ErrorCode.ORDER_NOT_FOUND.value,
        error_code=ErrorCode.ORDER_NOT_FOUND.value,
        eligible=False,
        needs_clarification=False,
        needs_manual_review=False,
        can_create_return_request=False,
        handoff_required=False,
        matched_rule_codes=[],
        deadline_at=None,
        rule_version=RULE_VERSION,
        required_materials=list(materials_for(reason_code)),
        next_action="explain_rules",
        eligibility_token=None,
        eligibility_expires_at=None,
        evaluated_at=now,
    )


__all__ = ["MESSAGES", "RETURN_NOTICE", "ReturnTools", "message_for", "request_hash"]
