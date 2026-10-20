"""Tool dispatcher: wires every registered tool to its DB-backed dependencies.

This is the single place that turns a ``(tool_name, payload, context)`` into an executed
``ToolResult``. The REST endpoints (returns/handoff) and the chat service both call through
here, so a tool can never be reached without its reader/store/writer and the audit sink.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.db.repositories.audit import AuditRepository
from shopmate_ecommerce_assistant.db.repositories.catalog import CatalogRepository
from shopmate_ecommerce_assistant.db.repositories.handoff import HandoffRepository
from shopmate_ecommerce_assistant.db.repositories.idempotency import IdempotencyRepository
from shopmate_ecommerce_assistant.db.repositories.orders import OrderRepository
from shopmate_ecommerce_assistant.db.repositories.returns import ReturnRepository
from shopmate_ecommerce_assistant.tools.catalog_tools import CatalogTools
from shopmate_ecommerce_assistant.tools.context import ToolContext
from shopmate_ecommerce_assistant.tools.handoff_tools import HandoffTools
from shopmate_ecommerce_assistant.tools.order_tools import OrderTools
from shopmate_ecommerce_assistant.tools.return_tools import ReturnTools
from shopmate_ecommerce_assistant.tools.schemas import ToolResult


class ToolDispatcher:
    """Executes any registered tool against DB-backed readers/stores/writers."""

    def __init__(self, *, session: AsyncSession, settings: Settings) -> None:
        catalog_reader = CatalogRepository(session)
        order_reader = OrderRepository(session)
        audit = AuditRepository(session)
        idempotency = IdempotencyRepository(session)

        self._catalog = CatalogTools(catalog_reader)
        self._order = OrderTools(order_reader)
        self._return = ReturnTools(
            order_reader,
            store=idempotency,
            writer=ReturnRepository(session),
            token_secret=settings.tool_token_secret,
            token_ttl_seconds=settings.eligibility_token_ttl_seconds,
            low_confidence_threshold=settings.intent_min_confidence,
            audit=audit,
        )
        self._handoff = HandoffTools(
            order_reader,
            store=idempotency,
            writer=HandoffRepository(session),
            audit=audit,
        )

    async def invoke(self, tool_name: str, payload: Any, *, context: ToolContext) -> ToolResult:
        """Execute one registered tool and return its envelope."""
        if tool_name in {
            "search_products",
            "get_product_detail",
            "compare_products",
            "check_stock",
        }:
            return await self._catalog_invoke(tool_name, payload, context)
        if tool_name == "get_order_status":
            return await self._order.get_order_status(payload, context=context)
        if tool_name == "get_shipment":
            return await self._order.get_shipment(payload, context=context)
        if tool_name == "check_return_eligibility":
            return await self._return.check_return_eligibility(payload, context=context)
        if tool_name == "create_return_request":
            return await self._return.create_return_request(payload, context=context)
        if tool_name == "create_handoff_ticket":
            return await self._handoff.create_handoff_ticket(payload, context=context)
        from uuid import uuid4

        from shopmate_ecommerce_assistant.core.errors import ErrorCode
        from shopmate_ecommerce_assistant.tools.schemas import ToolFailure

        return ToolFailure(
            tool_call_id=uuid4(),
            error_code=ErrorCode.VALIDATION_ERROR.value,
            user_message="不支持的工具调用。",
            trace_id=context.trace_id,
        )

    async def _catalog_invoke(
        self, tool_name: str, payload: Any, context: ToolContext
    ) -> ToolResult:
        if tool_name == "search_products":
            return await self._catalog.search_products(payload, context=context)
        if tool_name == "get_product_detail":
            return await self._catalog.get_product_detail(payload, context=context)
        if tool_name == "compare_products":
            return await self._catalog.compare_products(payload, context=context)
        return await self._catalog.check_stock(payload, context=context)


__all__ = ["ToolDispatcher"]
