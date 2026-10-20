"""Redaction and summarisation for ``tool_calls`` audit rows.

Two rules drive this module:

* the audit row must be useful for support (which tool, which resource, what happened,
  how long it took, which idempotency key), so identifiers and outcome codes are kept;
* it must never contain raw user text, a phone number, an address, a token or an
  idempotency key in clear, so strings are PII-masked, truncated and keys are digested.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from shopmate_ecommerce_assistant.safety.pii import mask_pii
from shopmate_ecommerce_assistant.tools.schemas import ToolResult

MAX_AUDIT_STRING_CHARS = 160

#: Fields each tool may record. Everything else is dropped, so a future schema addition
#: cannot silently leak into the audit trail.
TOOL_INPUT_FIELDS: dict[str, tuple[str, ...]] = {
    "search_products": ("query", "category", "brand", "limit", "in_stock_only"),
    "get_product_detail": ("product_id", "variant_id"),
    "compare_products": ("product_ids",),
    "check_stock": ("variant_id", "quantity"),
    "get_order_status": ("order_id", "order_no"),
    "get_shipment": ("order_id",),
    "check_return_eligibility": (
        "order_id",
        "order_item_id",
        "reason_code",
    ),
    "create_return_request": ("order_id", "order_item_id", "reason_code"),
    "create_handoff_ticket": ("conversation_id", "reason_code", "summary_redacted"),
}

_SAFE_SCALARS = (bool, int, float)


def digest_key(key: str) -> str:
    """Return a short, non-reversible digest of an idempotency key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _redact_value(value: Any) -> Any:
    if value is None or isinstance(value, _SAFE_SCALARS):
        return value
    if isinstance(value, str):
        masked, _ = mask_pii(value)
        return masked[:MAX_AUDIT_STRING_CHARS]
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value[:10]]
    return _redact_value(str(value))


def redact_tool_input(
    tool_name: str, payload: Any, *, idempotency_key: str | None = None
) -> dict[str, Any]:
    """Return the allow-listed, PII-masked view of a tool's input.

    ``idempotency_key`` is injected server-side (``ToolContext``), so the runtime passes it
    in here rather than reading it from the payload; the payload fallback keeps the digest
    for callers that still supply the key inline.
    """
    if isinstance(payload, BaseModel):
        raw: Mapping[str, Any] = payload.model_dump(mode="json")
    elif isinstance(payload, Mapping):
        raw = payload
    else:
        return {}

    allowed = TOOL_INPUT_FIELDS.get(tool_name, ())
    redacted = {
        key: _redact_value(raw[key]) for key in allowed if key in raw and raw[key] is not None
    }
    key = idempotency_key or raw.get("idempotency_key")
    if isinstance(key, str) and key:
        redacted["idempotency_key_digest"] = digest_key(key)
    return redacted


def summarize_result(tool_name: str, result: ToolResult) -> dict[str, Any]:
    """Return the minimal result summary stored next to the call."""
    if not result.ok:
        return {"ok": False, "error_code": result.error_code}
    data = result.data
    tool = tool_name
    if tool == "get_order_status":
        return {
            "ok": True,
            "order_id": data.get("order_id"),
            "status": data.get("status"),
            "timeline_events": len(data.get("timeline") or []),
        }
    if tool == "get_shipment":
        return {
            "ok": True,
            "shipment_id": data.get("shipment_id"),
            "status": data.get("status"),
            "events": len(data.get("events") or []),
        }
    if tool == "check_return_eligibility":
        return {
            "ok": True,
            "decision": data.get("decision"),
            "decision_code": data.get("decision_code"),
            "matched_rule_codes": list(data.get("matched_rule_codes") or [])[:8],
        }
    if tool == "create_return_request":
        return {
            "ok": True,
            "return_request_id": data.get("return_request_id"),
            "status": data.get("status"),
            "refund_status": data.get("refund_status"),
        }
    if tool == "create_handoff_ticket":
        return {
            "ok": True,
            "ticket_id": data.get("ticket_id"),
            "status": data.get("status"),
            "risk_level": data.get("risk_level"),
            "priority": data.get("priority"),
            "primary_reason_code": data.get("primary_reason_code"),
        }
    return {"ok": True, "fields": sorted(data)[:10]}


__all__ = [
    "MAX_AUDIT_STRING_CHARS",
    "TOOL_INPUT_FIELDS",
    "digest_key",
    "redact_tool_input",
    "summarize_result",
]
