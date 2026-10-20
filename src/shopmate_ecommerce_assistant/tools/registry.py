"""Tool registry.

Only the names listed here can be executed. There is no dynamic dispatch by dotted path,
no "call any function" escape hatch and no way to reach the database without a registered
input schema.

Stage 9 registers the order, return and handoff tools next to the catalog tools, so the
router's ``ALLOWED_TOOLS`` and the executable set can be compared in a test. The chat
dispatcher that wires reader/store/writer into these tools is stage 10; this module stays a
pure registry.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from shopmate_ecommerce_assistant.core.errors import ErrorCode
from shopmate_ecommerce_assistant.domain.catalog.ports import CatalogReader
from shopmate_ecommerce_assistant.tools.catalog_tools import CatalogTools
from shopmate_ecommerce_assistant.tools.context import ToolContext
from shopmate_ecommerce_assistant.tools.order_schemas import (
    CheckReturnEligibilityInput,
    CreateHandoffTicketInput,
    CreateReturnRequestInput,
    GetOrderStatusInput,
    GetShipmentInput,
)
from shopmate_ecommerce_assistant.tools.runtime import utc_now
from shopmate_ecommerce_assistant.tools.schemas import (
    CheckStockInput,
    CompareProductsInput,
    GetProductDetailInput,
    SearchProductsInput,
    ToolFailure,
    ToolResult,
)

CATALOG_TOOL_MODELS: dict[str, type[BaseModel]] = {
    "search_products": SearchProductsInput,
    "get_product_detail": GetProductDetailInput,
    "compare_products": CompareProductsInput,
    "check_stock": CheckStockInput,
}

ORDER_TOOL_MODELS: dict[str, type[BaseModel]] = {
    "get_order_status": GetOrderStatusInput,
    "get_shipment": GetShipmentInput,
    "check_return_eligibility": CheckReturnEligibilityInput,
    "create_return_request": CreateReturnRequestInput,
    "create_handoff_ticket": CreateHandoffTicketInput,
}

TOOL_MODELS: dict[str, type[BaseModel]] = {**CATALOG_TOOL_MODELS, **ORDER_TOOL_MODELS}

READ_ONLY_TOOLS = frozenset(CATALOG_TOOL_MODELS) | frozenset(
    {"get_order_status", "get_shipment", "check_return_eligibility"}
)

#: The only two tools with a database side effect. Neither can approve money.
WRITE_TOOLS = frozenset({"create_return_request", "create_handoff_ticket"})


def tool_names() -> tuple[str, ...]:
    """Return every registered tool name, catalog first, in contract order."""
    return tuple(TOOL_MODELS)


def catalog_tool_names() -> tuple[str, ...]:
    """Return only the stage-6 catalog tools."""
    return tuple(CATALOG_TOOL_MODELS)


def is_registered(name: str) -> bool:
    """Return True when ``name`` may be executed."""
    return name in TOOL_MODELS


def input_schema(name: str) -> dict[str, Any]:
    """Return the JSON schema of a registered tool's input.

    Raises:
        KeyError: when the tool is not registered.
    """
    return TOOL_MODELS[name].model_json_schema()


async def invoke_catalog_tool(
    name: str,
    payload: Any,
    *,
    context: ToolContext,
    reader: CatalogReader,
    clock: Callable[[], datetime] = utc_now,
) -> ToolResult:
    """Execute one registered catalog tool and always return an envelope."""
    if name not in CATALOG_TOOL_MODELS:
        return ToolFailure(
            tool_call_id=uuid4(),
            error_code=ErrorCode.VALIDATION_ERROR.value,
            user_message="不支持的工具调用。",
            trace_id=context.trace_id,
        )

    tools = CatalogTools(reader, clock=clock)
    handlers = {
        "search_products": tools.search_products,
        "get_product_detail": tools.get_product_detail,
        "compare_products": tools.compare_products,
        "check_stock": tools.check_stock,
    }
    return await handlers[name](payload, context=context)


__all__ = [
    "CATALOG_TOOL_MODELS",
    "ORDER_TOOL_MODELS",
    "READ_ONLY_TOOLS",
    "TOOL_MODELS",
    "WRITE_TOOLS",
    "catalog_tool_names",
    "input_schema",
    "invoke_catalog_tool",
    "is_registered",
    "tool_names",
]
