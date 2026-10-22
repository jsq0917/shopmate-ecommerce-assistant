"""Integration tests: search results must equal PostgreSQL price and stock facts."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa

from shopmate_ecommerce_assistant.db.models import Inventory, Product, ProductVariant, UserRole
from shopmate_ecommerce_assistant.db.repositories.catalog import CatalogRepository
from shopmate_ecommerce_assistant.synthetic.catalog_data import shop_id
from shopmate_ecommerce_assistant.synthetic.seed import run_seed
from shopmate_ecommerce_assistant.tools.catalog_tools import CatalogTools
from shopmate_ecommerce_assistant.tools.context import ToolContext

pytestmark = pytest.mark.integration


def _tools(session, *, shop=None) -> tuple[CatalogTools, ToolContext]:
    context = ToolContext(
        shop_id=shop or shop_id(),
        actor_user_id=uuid4(),
        role=UserRole.SHOPPER,
        request_id=uuid4(),
        trace_id=uuid4(),
    )
    return CatalogTools(CatalogRepository(session)), context


async def test_search_cards_match_database_price_and_stock(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)

    result = await tools.search_products(
        {"query": "降噪耳机", "budget_max_cents": 30000, "limit": 10}, context=context
    )

    assert result.ok is True
    items = result.data["items"]
    assert items, "300 元以内的降噪耳机应至少命中一款"

    for card in items:
        row = (
            await session.execute(
                sa.select(
                    ProductVariant.product_id,
                    ProductVariant.price_cents,
                    ProductVariant.currency,
                    sa.func.sum(Inventory.available_qty),
                )
                .outerjoin(Inventory, Inventory.variant_id == ProductVariant.id)
                .where(
                    ProductVariant.id == UUID(card["variant_id"]),
                    ProductVariant.shop_id == shop_id(),
                )
                .group_by(
                    ProductVariant.product_id,
                    ProductVariant.price_cents,
                    ProductVariant.currency,
                )
            )
        ).one()

        assert card["product_id"] == str(row[0])
        assert card["price_cents"] == row[1]
        assert card["currency"] == row[2]
        assert card["available_qty"] == row[3]
        assert card["price_cents"] <= 30000
        assert isinstance(card["price_cents"], int)
        assert card["is_synthetic"] is True


async def test_search_applies_budget_lower_bound_inclusively(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)

    result = await tools.search_products(
        {"query": "耳机", "budget_min_cents": 24900, "budget_max_cents": 24900, "limit": 20},
        context=context,
    )

    assert result.ok is True
    assert result.data["items"]
    assert all(card["price_cents"] == 24900 for card in result.data["items"])


async def test_search_filters_category_brand_and_attributes(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)

    result = await tools.search_products(
        {
            "query": "耳机",
            "category": "耳机",
            "brand": "声岚",
            "attributes": {"noise_cancelling": True},
            "limit": 20,
        },
        context=context,
    )

    assert result.ok is True
    items = result.data["items"]
    assert items
    assert all("耳机" in card["category"] for card in items)
    assert all(card["brand"] == "声岚" for card in items)
    assert all(card["attributes"]["noise_cancelling"] is True for card in items)
    assert "属性匹配" in items[0]["matched_reasons"]


async def test_in_stock_filter_never_returns_zero_stock(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)

    result = await tools.search_products(
        {"query": "耳机", "in_stock_only": True, "limit": 20}, context=context
    )

    assert result.ok is True
    assert result.data["items"]
    assert all(card["stock_status"] == "in_stock" for card in result.data["items"])
    assert all(card["available_qty"] >= 1 for card in result.data["items"])


async def test_search_limit_and_truncated_flag(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)

    result = await tools.search_products({"query": "耳机", "limit": 2}, context=context)

    assert result.ok is True
    assert len(result.data["items"]) == 2
    assert result.data["truncated"] is True


async def test_query_strings_are_parameters_not_sql(session) -> None:
    await run_seed(session)
    tools, context = _tools(session)

    injection = await tools.search_products(
        {"query": "'; drop table products; --", "limit": 5}, context=context
    )
    wildcard = await tools.search_products(
        {"query": "耳机", "category": "%", "brand": "' OR '1'='1", "limit": 5}, context=context
    )

    assert injection.ok is True
    assert injection.data["items"] == []
    assert wildcard.ok is True
    assert wildcard.data["items"] == []

    remaining = await session.scalar(sa.select(sa.func.count()).select_from(Product))
    # The catalog grew in stage 17; the invariant is "injection never removed a row".
    assert remaining >= 30


async def test_catalog_queries_are_shop_scoped(session) -> None:
    await run_seed(session)
    other_shop = uuid4()
    tools, other_context = _tools(session, shop=other_shop)

    empty = await tools.search_products({"query": "耳机", "limit": 5}, context=other_context)
    assert empty.ok is True
    assert empty.data["items"] == []

    demo_product_id = await session.scalar(
        sa.select(Product.id).where(Product.shop_id == shop_id()).limit(1)
    )
    denied = await tools.get_product_detail(
        {"product_id": str(demo_product_id)}, context=other_context
    )
    assert denied.ok is False
    assert denied.error_code == "PRODUCT_NOT_FOUND"
