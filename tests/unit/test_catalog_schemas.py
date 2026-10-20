"""Strict schema tests for the catalog tools: bounds, unknown fields and vocabularies."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from shopmate_ecommerce_assistant.domain.catalog.attributes import DEFAULT_COMPARE_KEYS
from shopmate_ecommerce_assistant.tools.schemas import (
    CheckStockInput,
    CompareProductsInput,
    GetProductDetailInput,
    SearchProductsInput,
)


def test_search_input_defaults_are_conservative() -> None:
    params = SearchProductsInput(query="降噪耳机")

    assert params.limit == 10
    assert params.in_stock_only is False
    assert params.budget_max_cents is None
    assert params.attributes is None


@pytest.mark.parametrize("limit", [0, 21, -1])
def test_search_limit_is_bounded_to_20(limit: int) -> None:
    with pytest.raises(ValidationError):
        SearchProductsInput(query="降噪耳机", limit=limit)


@pytest.mark.parametrize("query", ["", "   ", "x" * 201])
def test_search_query_must_be_present_and_bounded(query: str) -> None:
    with pytest.raises(ValidationError):
        SearchProductsInput(query=query)


def test_search_rejects_inverted_budget() -> None:
    with pytest.raises(ValidationError):
        SearchProductsInput(query="耳机", budget_min_cents=30000, budget_max_cents=10000)


def test_search_accepts_zero_as_a_valid_budget_boundary() -> None:
    params = SearchProductsInput(query="耳机", budget_min_cents=0, budget_max_cents=0)

    assert params.budget_min_cents == 0
    assert params.budget_max_cents == 0


def test_search_rejects_unknown_attribute_keys() -> None:
    with pytest.raises(ValidationError):
        SearchProductsInput(query="耳机", attributes={"cpu_model": "M1"})


def test_search_rejects_more_than_ten_attribute_filters() -> None:
    attributes = {
        "connectivity": "蓝牙 5.3",
        "battery_hours": 40,
        "weight_g": 200,
        "warranty_months": 12,
        "layout": "87 键",
        "switch": "红轴",
        "backlight": "白色背光",
        "dpi": 4000,
        "power_w": 65,
        "ports": 2,
        "color": "曜石黑",
    }
    with pytest.raises(ValidationError):
        SearchProductsInput(query="耳机", attributes=attributes)


def test_search_normalizes_attribute_aliases() -> None:
    params = SearchProductsInput(query="降噪耳机", attributes={"noise_cancellation": True})

    assert params.attributes == {"noise_cancelling": True}


def test_search_forbids_identity_and_sql_fields() -> None:
    with pytest.raises(ValidationError):
        SearchProductsInput(query="耳机", shop_id=uuid4())  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        SearchProductsInput(query="耳机", sql="select 1")  # type: ignore[call-arg]


def test_detail_accepts_optional_variant() -> None:
    product_id = uuid4()

    assert GetProductDetailInput(product_id=product_id).variant_id is None


def test_compare_requires_two_to_four_unique_products() -> None:
    product_id = uuid4()

    with pytest.raises(ValidationError):
        CompareProductsInput(product_ids=[product_id])
    with pytest.raises(ValidationError):
        CompareProductsInput(product_ids=[product_id] * 2)
    with pytest.raises(ValidationError):
        CompareProductsInput(product_ids=[uuid4() for _ in range(5)])


def test_compare_defaults_and_alias_normalization() -> None:
    ids = [uuid4(), uuid4()]

    assert CompareProductsInput(product_ids=ids).attributes == list(DEFAULT_COMPARE_KEYS)
    assert CompareProductsInput(product_ids=ids, attributes=["price"]).attributes == ["price"]
    assert CompareProductsInput(
        product_ids=ids, attributes=["noise_cancellation", "price", "price"]
    ).attributes == ["noise_cancelling", "price"]


def test_compare_rejects_unknown_dimension() -> None:
    with pytest.raises(ValidationError):
        CompareProductsInput(product_ids=[uuid4(), uuid4()], attributes=["cpu_benchmark"])


def test_check_stock_quantity_bounds() -> None:
    variant_id = uuid4()

    assert CheckStockInput(variant_id=variant_id).quantity == 1
    with pytest.raises(ValidationError):
        CheckStockInput(variant_id=variant_id, quantity=0)
    with pytest.raises(ValidationError):
        CheckStockInput(variant_id=variant_id, quantity=1000)


def test_check_stock_forbids_user_identity() -> None:
    with pytest.raises(ValidationError):
        CheckStockInput(variant_id=uuid4(), user_id=uuid4())  # type: ignore[call-arg]
