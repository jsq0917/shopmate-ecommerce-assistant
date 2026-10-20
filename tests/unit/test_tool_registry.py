"""Registry consistency: every route-authorized tool is executable, writes are isolated."""

from __future__ import annotations

from shopmate_ecommerce_assistant.agents.router import ALLOWED_TOOLS
from shopmate_ecommerce_assistant.tools import registry


def test_nine_tools_are_registered() -> None:
    assert registry.tool_names() == (
        "search_products",
        "get_product_detail",
        "compare_products",
        "check_stock",
        "get_order_status",
        "get_shipment",
        "check_return_eligibility",
        "create_return_request",
        "create_handoff_ticket",
    )


def test_write_tools_are_exactly_the_two_safe_writes() -> None:
    assert registry.WRITE_TOOLS == frozenset({"create_return_request", "create_handoff_ticket"})


def test_every_route_authorized_tool_is_registered() -> None:
    allowed = {name for names in ALLOWED_TOOLS.values() for name in names}
    # ``get_promotion`` is the only stage-6 tool still pending; everything the router may
    # actually dispatch today must exist.
    assert allowed - {"get_promotion"} <= set(registry.tool_names())


def test_write_tools_are_not_in_read_only_set() -> None:
    assert not (registry.WRITE_TOOLS & registry.READ_ONLY_TOOLS)


def test_identity_is_not_in_any_input_schema() -> None:
    forbidden = {"shop_id", "user_id", "risk_level", "confirmation_state"}
    for name in registry.tool_names():
        schema = registry.input_schema(name)
        properties = schema.get("properties", {})
        assert not (forbidden & set(properties)), name


def test_server_injected_fields_are_not_in_input_schemas() -> None:
    """The router/API inject these; a model must not be able to forge them (contract §5.9)."""
    forbidden = {"idempotency_key", "confidence", "clarification_attempted"}
    for name in registry.tool_names():
        schema = registry.input_schema(name)
        properties = schema.get("properties", {})
        assert not (forbidden & set(properties)), name


def test_unknown_tool_is_not_registered() -> None:
    assert registry.is_registered("run_sql") is False
    assert registry.is_registered("approve_refund") is False
