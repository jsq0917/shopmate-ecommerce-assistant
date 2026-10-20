"""Unit tests for audit redaction and result summarisation."""

from __future__ import annotations

from uuid import uuid4

from shopmate_ecommerce_assistant.tools.audit import (
    digest_key,
    redact_tool_input,
    summarize_result,
)
from shopmate_ecommerce_assistant.tools.schemas import ToolFailure, ToolSuccess


def test_redact_keeps_only_allowlisted_fields() -> None:
    redacted = redact_tool_input(
        "get_order_status",
        {"order_id": "abc", "order_no": "SM-1", "shop_id": "secret", "sql": "DROP TABLE x"},
    )
    assert set(redacted) == {"order_id", "order_no"}
    assert "shop_id" not in redacted and "sql" not in redacted


def test_redact_masks_pii_in_strings() -> None:
    redacted = redact_tool_input(
        "create_handoff_ticket",
        {
            "conversation_id": "c",
            "reason_code": "COMPLAINT",
            "summary_redacted": "电话 13812345678 请回电",
        },
    )
    assert "13812345678" not in redacted["summary_redacted"]


def test_redact_digests_idempotency_key() -> None:
    redacted = redact_tool_input(
        "create_return_request",
        {
            "order_id": "o",
            "order_item_id": "i",
            "reason_code": "SIZE_OR_FIT",
            "idempotency_key": "return-key-0000000001",
        },
    )
    assert "idempotency_key" not in redacted
    assert redacted["idempotency_key_digest"] == digest_key("return-key-0000000001")


def test_digest_is_short_and_stable() -> None:
    assert digest_key("abc") == digest_key("abc")
    assert len(digest_key("abc")) == 16


def test_summarize_failure_has_only_error_code() -> None:
    summary = summarize_result(
        "get_order_status",
        ToolFailure(
            tool_call_id=uuid4(),
            error_code="ORDER_NOT_FOUND",
            user_message="x",
            trace_id=uuid4(),
        ),
    )
    assert summary == {"ok": False, "error_code": "ORDER_NOT_FOUND"}


def test_summarize_return_success_is_minimal() -> None:
    summary = summarize_result(
        "create_return_request",
        ToolSuccess(
            tool_call_id=uuid4(),
            data={
                "return_request_id": "r1",
                "status": "submitted",
                "refund_status": "not_created",
                "notice": "申请已提交，但尚未退款。",
            },
            as_of="2026-10-15T08:00:00Z",
            trace_id=uuid4(),
        ),
    )
    assert summary == {
        "ok": True,
        "return_request_id": "r1",
        "status": "submitted",
        "refund_status": "not_created",
    }
