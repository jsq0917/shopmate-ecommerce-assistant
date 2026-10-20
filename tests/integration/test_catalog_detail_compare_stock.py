"""Integration tests for detail, comparison and stock check against PostgreSQL."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa

from shopmate_ecommerce_assistant.core.ids import stable_uuid
from shopmate_ecommerce_assistant.db.models import Inventory, ProductVariant, UserRole
from shopmate_ecommerce_assistant.db.repositories.catalog import CatalogRepository
from shopmate_ecommerce_assistant.synthetic.catalog_data import shop_id
from shopmate_ecommerce_assistant.synthetic.seed import run_seed
from shopmate_ecommerce_assistant.tools.catalog_tools import CatalogTools
from shopmate_ecommerce_assistant.tools.context import ToolContext

pytestmark = pytest.mark.integration

NC300 = stable_uuid("product", "sl-nc300")
CABLE = stable_uuid("product", "l-20w")


def _tools(session, *, shop=None) -> tuple[CatalogTools, ToolContext]:
    context = ToolContext(
        shop_id=shop or shop_id(),
        actor_user_id=uuid4(),
        role=UserRole.SHOPPER,
        request_id=uuid4(),
        trace_id=uuid4(),
    )
    return CatalogTools(CatalogRepository(session)), context


async def _variant_rows(session, product_id: UUID) -> list[tuple[UUID, int, str]]:
    rows = await session.execute(
        sa.select(ProductVariant.id, ProductVariant.price_cents, ProductVariant.currency).where(
            ProductVariant.shop_id == shop_id(), ProductVariant.product_id == product_id
        )
    )
    return [(row[0], row[1], row[2]) for row in rows]


async def test_detail_lists_every_sku_with_real_price_and_stock(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)

    result = await tools.get_product_detail({"product_id": str(NC300)}, context=context)

    assert result.ok is True
    product = result.data["product"]
    db_variants = await _variant_rows(session, NC300)

    assert len(product["variants"]) == len(db_variants)
    prices = {UUID(item["id"]): item["price_cents"] for item in product["variants"]}
    for variant_id, price_cents, currency in db_variants:
        assert prices[variant_id] == price_cents
        assert currency == "CNY"
    assert product["is_synthetic"] is True

    stock_total = await session.scalar(
        sa.select(sa.func.sum(Inventory.available_qty))
        .join(ProductVariant, ProductVariant.id == Inventory.variant_id)
        .where(ProductVariant.product_id == NC300, ProductVariant.shop_id == shop_id())
    )
    assert product["stock_summary"]["available_qty"] == stock_total
    assert product["stock_summary"]["stock_status"] == "in_stock"

    newest = await session.scalar(
        sa.select(sa.func.max(Inventory.updated_at))
        .join(ProductVariant, ProductVariant.id == Inventory.variant_id)
        .where(ProductVariant.product_id == NC300, ProductVariant.shop_id == shop_id())
    )
    assert product["stock_summary"]["updated_at"] is not None
    assert result.as_of == newest


async def test_detail_can_select_one_variant(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)
    variant_ids = [row[0] for row in await _variant_rows(session, NC300)]

    result = await tools.get_product_detail(
        {"product_id": str(NC300), "variant_id": str(variant_ids[0])}, context=context
    )

    assert result.ok is True
    assert [item["id"] for item in result.data["product"]["variants"]] == [str(variant_ids[0])]


async def test_detail_rejects_variant_from_another_product(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)
    other_variant = (await _variant_rows(session, CABLE))[0][0]

    result = await tools.get_product_detail(
        {"product_id": str(NC300), "variant_id": str(other_variant)}, context=context
    )

    assert result.ok is False
    assert result.error_code == "VARIANT_NOT_FOUND"


async def test_compare_aligns_fields_and_marks_missing_unknown(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)

    result = await tools.compare_products(
        {
            "product_ids": [str(NC300), str(CABLE)],
            "attributes": ["battery_hours", "price", "dpi", "color"],
        },
        context=context,
    )

    assert result.ok is True
    rows = {row["key"]: row for row in result.data["rows"]}
    assert list(rows) == ["battery_hours", "price", "dpi", "color"]

    headphone_price = (await _variant_rows(session, NC300))[0][1]
    cable_price = (await _variant_rows(session, CABLE))[0][1]
    assert rows["price"]["values"][0]["value"] == headphone_price
    assert rows["price"]["values"][1]["value"] == cable_price

    cable_battery = rows["battery_hours"]["values"][1]
    assert cable_battery["known"] is False
    assert cable_battery["value"] is None
    assert cable_battery["display"] == "unknown"

    assert rows["dpi"]["values"][0]["known"] is False
    assert rows["battery_hours"]["values"][0]["known"] is True

    # Both products carry a colour on the seeded SKU, so it must not be invented as unknown.
    assert rows["color"]["values"][0]["known"] is True


async def test_compare_defaults_to_contract_dimensions(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)

    result = await tools.compare_products(
        {"product_ids": [str(NC300), str(CABLE)]}, context=context
    )

    assert result.ok is True
    assert [row["key"] for row in result.data["rows"]] == [
        "price",
        "brand",
        "category",
        "stock_status",
    ]
    assert [product["product_id"] for product in result.data["products"]] == [
        str(NC300),
        str(CABLE),
    ]


async def test_compare_rejects_missing_product(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)

    result = await tools.compare_products(
        {"product_ids": [str(NC300), str(uuid4())]}, context=context
    )

    assert result.ok is False
    assert result.error_code == "PRODUCT_NOT_FOUND"


async def test_check_stock_matches_inventory_rows(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)
    variant_id, available_qty = (
        await session.execute(
            sa.select(Inventory.variant_id, Inventory.available_qty)
            .where(Inventory.shop_id == shop_id(), Inventory.available_qty > 0)
            .limit(1)
        )
    ).one()

    result = await tools.check_stock(
        {"variant_id": str(variant_id), "quantity": 1}, context=context
    )

    assert result.ok is True
    assert result.data["available_qty"] == available_qty
    assert result.data["is_available"] is True
    assert result.data["stock_status"] == "in_stock"
    warehouses = result.data["warehouses"]
    assert len(warehouses) == 1
    assert warehouses[0]["available_qty"] == available_qty
    assert warehouses[0]["updated_at"] is not None


async def test_check_stock_reports_shortage_without_pretending(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)
    variant_id, available_qty = (
        await session.execute(
            sa.select(Inventory.variant_id, Inventory.available_qty)
            .where(Inventory.shop_id == shop_id(), Inventory.available_qty > 0)
            .limit(1)
        )
    ).one()

    result = await tools.check_stock(
        {"variant_id": str(variant_id), "quantity": available_qty + 1}, context=context
    )

    assert result.ok is True
    assert result.data["is_available"] is False
    assert result.data["available_qty"] == available_qty


async def test_check_stock_out_of_stock_variant(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)
    variant_id = await session.scalar(
        sa.select(Inventory.variant_id)
        .where(Inventory.shop_id == shop_id(), Inventory.available_qty == 0)
        .limit(1)
    )
    assert variant_id is not None

    result = await tools.check_stock({"variant_id": str(variant_id)}, context=context)

    assert result.ok is True
    assert result.data["available_qty"] == 0
    assert result.data["is_available"] is False
    assert result.data["stock_status"] == "out_of_stock"


async def test_check_stock_is_shop_scoped(session) -> None:
    await run_seed(session)
    tools, context = _tools(session, shop=uuid4())
    variant_id = await session.scalar(
        sa.select(Inventory.variant_id).where(Inventory.shop_id == shop_id()).limit(1)
    )

    result = await tools.check_stock({"variant_id": str(variant_id)}, context=context)

    assert result.ok is False
    assert result.error_code == "VARIANT_NOT_FOUND"
