"""Unit tests for the catalog tool boundary using a fake reader (no database)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError

from shopmate_ecommerce_assistant.db.models.enums import UserRole
from shopmate_ecommerce_assistant.domain.catalog.compare import CompareSource
from shopmate_ecommerce_assistant.domain.catalog.models import (
    ProductHit,
    ProductSnapshot,
    SearchCriteria,
    VariantSnapshot,
    WarehouseStock,
)
from shopmate_ecommerce_assistant.tools.catalog_tools import CatalogTools
from shopmate_ecommerce_assistant.tools.context import ToolContext
from shopmate_ecommerce_assistant.tools.registry import invoke_catalog_tool

STOCK_AT = datetime(2026, 10, 18, 11, 59, 30, tzinfo=UTC)


def _context(role: UserRole = UserRole.SHOPPER) -> ToolContext:
    return ToolContext(
        shop_id=uuid4(),
        actor_user_id=uuid4(),
        role=role,
        request_id=uuid4(),
        trace_id=uuid4(),
    )


def _hit(*, price_cents: int = 29900, available_qty: int | None = 12) -> ProductHit:
    product_id = uuid4()
    return ProductHit(
        product=ProductSnapshot(
            id=product_id,
            title="声岚 SL-NC300 入耳式降噪耳机",
            description="入耳式主动降噪。",
            brand="声岚",
            category="降噪耳机",
            attributes={"battery_hours": 24, "noise_cancelling": True},
            status="active",
            is_synthetic=True,
        ),
        variant=VariantSnapshot(
            id=uuid4(),
            product_id=product_id,
            sku="SM-SL-NC300-01",
            title="声岚 SL-NC300 · 曜石黑",
            attributes={"color": "曜石黑"},
            price_cents=price_cents,
            currency="CNY",
            status="active",
            available_qty=available_qty,
            stock_updated_at=STOCK_AT,
        ),
    )


class FakeReader:
    """Configurable stand-in for :class:`CatalogReader`."""

    def __init__(self) -> None:
        self.hits: list[ProductHit] = []
        self.product: ProductSnapshot | None = None
        self.variants: list[VariantSnapshot] = []
        self.variant: VariantSnapshot | None = None
        self.sources: list[CompareSource] = []
        self.error: Exception | None = None
        self.search_calls: list[tuple[UUID, SearchCriteria, int]] = []

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error

    async def search(
        self, *, shop_id: UUID, criteria: SearchCriteria, limit: int
    ) -> list[ProductHit]:
        self.search_calls.append((shop_id, criteria, limit))
        self._raise()
        return self.hits[:limit]

    async def get_product(self, *, shop_id: UUID, product_id: UUID) -> ProductSnapshot | None:
        self._raise()
        if self.product is not None and self.product.id == product_id:
            return self.product
        return None

    async def list_variants(
        self, *, shop_id: UUID, product_id: UUID, variant_id: UUID | None = None
    ) -> list[VariantSnapshot]:
        self._raise()
        if variant_id is None:
            return list(self.variants)
        return [variant for variant in self.variants if variant.id == variant_id]

    async def get_variant(self, *, shop_id: UUID, variant_id: UUID) -> VariantSnapshot | None:
        self._raise()
        if self.variant is not None and self.variant.id == variant_id:
            return self.variant
        return None

    async def load_compare_sources(
        self, *, shop_id: UUID, product_ids: Sequence[UUID]
    ) -> list[CompareSource]:
        self._raise()
        return list(self.sources)


async def test_search_validation_failure_never_reaches_the_repository() -> None:
    reader = FakeReader()
    tools = CatalogTools(reader)
    context = _context()

    result = await tools.search_products({"query": "耳机", "limit": 21}, context=context)

    assert result.ok is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.trace_id == context.trace_id
    assert "pydantic" not in result.user_message.lower()
    assert reader.search_calls == []


async def test_search_returns_a_card_built_from_snapshot_facts() -> None:
    reader = FakeReader()
    reader.hits = [_hit()]
    tools = CatalogTools(reader)
    context = _context()

    result = await tools.search_products(
        {"query": "降噪耳机", "budget_max_cents": 30000, "limit": 5}, context=context
    )

    assert result.ok is True
    assert result.source == "postgres"
    assert result.trace_id == context.trace_id
    card = result.data["items"][0]
    assert card["price_cents"] == 29900
    assert card["available_qty"] == 12
    assert card["stock_status"] == "in_stock"
    assert card["attributes"]["color"] == "曜石黑"
    assert card["as_of"].startswith("2026-10-18T11:59:30")
    assert "预算内" in card["matched_reasons"]
    assert result.data["truncated"] is False


async def test_search_reports_unknown_stock_instead_of_zero() -> None:
    reader = FakeReader()
    reader.hits = [_hit(available_qty=None)]
    tools = CatalogTools(reader)

    result = await tools.search_products({"query": "降噪"}, context=_context())

    card = result.data["items"][0]
    assert card["available_qty"] is None
    assert card["stock_status"] == "unknown"
    assert "有货" not in card["matched_reasons"]


async def test_search_truncates_and_flags_more_results() -> None:
    reader = FakeReader()
    reader.hits = [_hit(price_cents=price) for price in (10000, 20000, 30000)]
    tools = CatalogTools(reader)

    result = await tools.search_products({"query": "降噪", "limit": 2}, context=_context())

    assert len(result.data["items"]) == 2
    assert result.data["truncated"] is True


async def test_database_failure_becomes_upstream_unavailable() -> None:
    reader = FakeReader()
    reader.error = SQLAlchemyError("connection reset")
    tools = CatalogTools(reader)

    result = await tools.search_products({"query": "耳机"}, context=_context())

    assert result.ok is False
    assert result.error_code == "UPSTREAM_UNAVAILABLE"
    assert result.retryable is True
    assert "connection reset" not in result.user_message


async def test_detail_not_found_and_variant_not_found() -> None:
    reader = FakeReader()
    tools = CatalogTools(reader)

    missing = await tools.get_product_detail({"product_id": str(uuid4())}, context=_context())
    assert missing.ok is False
    assert missing.error_code == "PRODUCT_NOT_FOUND"

    reader.product = _hit().product
    reader.variants = []
    wrong_variant = await tools.get_product_detail(
        {"product_id": str(reader.product.id), "variant_id": str(uuid4())},
        context=_context(),
    )
    assert wrong_variant.ok is False
    assert wrong_variant.error_code == "VARIANT_NOT_FOUND"


async def test_detail_summarises_known_stock() -> None:
    hit = _hit(available_qty=6)
    reader = FakeReader()
    reader.product = hit.product
    reader.variants = [hit.variant]
    tools = CatalogTools(reader)

    result = await tools.get_product_detail({"product_id": str(hit.product.id)}, context=_context())

    assert result.ok is True
    summary = result.data["product"]["stock_summary"]
    assert summary["available_qty"] == 6
    assert summary["stock_status"] == "in_stock"
    assert result.data["product"]["variants"][0]["price_cents"] == 29900


async def test_compare_rejects_unknown_product_without_leaking_it() -> None:
    reader = FakeReader()
    reader.sources = []
    tools = CatalogTools(reader)

    result = await tools.compare_products(
        {"product_ids": [str(uuid4()), str(uuid4())]}, context=_context()
    )

    assert result.ok is False
    assert result.error_code == "PRODUCT_NOT_FOUND"
    assert "不存在" in result.user_message or "未找到" in result.user_message


async def test_compare_marks_missing_dimension_unknown() -> None:
    left = _hit()
    reader = FakeReader()
    reader.sources = [
        CompareSource(
            product_id=left.product.id,
            title=left.product.title,
            variant_id=left.variant.id,
            variant_title=left.variant.title,
            price_cents=left.variant.price_cents,
            currency="CNY",
            brand="声岚",
            category="降噪耳机",
            product_attributes={"battery_hours": 24},
            variant_attributes={},
            available_qty=12,
            stock_updated_at=STOCK_AT,
        ),
        CompareSource(
            product_id=uuid4(),
            title="速派 L 20W 数据线",
            variant_id=uuid4(),
            variant_title="速派 L 20W",
            price_cents=2900,
            currency="CNY",
            brand="速派",
            category="数据线",
            product_attributes={"power_w": 20},
            variant_attributes={},
            available_qty=0,
            stock_updated_at=STOCK_AT,
        ),
    ]
    tools = CatalogTools(reader)

    result = await tools.compare_products(
        {
            "product_ids": [str(source.product_id) for source in reader.sources],
            "attributes": ["battery_hours", "price", "stock_status"],
        },
        context=_context(),
    )

    assert result.ok is True
    rows = {row["key"]: row for row in result.data["rows"]}
    assert rows["battery_hours"]["values"][1]["known"] is False
    assert rows["battery_hours"]["values"][1]["display"] == "unknown"
    assert rows["price"]["values"][1]["value"] == 2900
    assert rows["stock_status"]["values"][1]["value"] == "out_of_stock"
    assert [row["key"] for row in result.data["rows"]] == [
        "battery_hours",
        "price",
        "stock_status",
    ]


async def test_check_stock_reports_true_quantity_when_short() -> None:
    hit = _hit(available_qty=2)
    variant = VariantSnapshot(
        id=hit.variant.id,
        product_id=hit.variant.product_id,
        sku=hit.variant.sku,
        title=hit.variant.title,
        attributes=hit.variant.attributes,
        price_cents=hit.variant.price_cents,
        currency="CNY",
        status="active",
        available_qty=2,
        stock_updated_at=STOCK_AT,
        warehouses=(WarehouseStock("WH-SH-01", 2, STOCK_AT),),
    )
    reader = FakeReader()
    reader.variant = variant
    tools = CatalogTools(reader)

    result = await tools.check_stock(
        {"variant_id": str(variant.id), "quantity": 5}, context=_context()
    )

    assert result.ok is True
    assert result.data["is_available"] is False
    assert result.data["available_qty"] == 2
    assert result.data["requested_qty"] == 5
    assert result.data["warehouses"][0]["warehouse_code"] == "WH-SH-01"


async def test_check_stock_unknown_variant() -> None:
    tools = CatalogTools(FakeReader())

    result = await tools.check_stock({"variant_id": str(uuid4())}, context=_context())

    assert result.ok is False
    assert result.error_code == "VARIANT_NOT_FOUND"


async def test_registry_rejects_unregistered_tool_names() -> None:
    result = await invoke_catalog_tool(
        "delete_all_products", {}, context=_context(), reader=FakeReader()
    )

    assert result.ok is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.user_message == "不支持的工具调用。"
