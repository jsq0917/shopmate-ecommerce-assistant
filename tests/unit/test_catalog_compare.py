"""Unit tests for the aligned comparison table (unknown handling, no fabrication)."""

from __future__ import annotations

from uuid import uuid4

from shopmate_ecommerce_assistant.domain.catalog.compare import CompareSource, build_rows


def _source(
    *,
    product_attributes: dict[str, object] | None = None,
    variant_attributes: dict[str, object] | None = None,
    price_cents: int | None = 29900,
    currency: str | None = "CNY",
    brand: str | None = "声岚",
    category: str | None = "降噪耳机",
    available_qty: int | None = 10,
) -> CompareSource:
    return CompareSource(
        product_id=uuid4(),
        title="示例商品",
        variant_id=None if price_cents is None else uuid4(),
        variant_title=None,
        price_cents=price_cents,
        currency=currency,
        brand=brand,
        category=category,
        product_attributes=product_attributes or {},
        variant_attributes=variant_attributes or {},
        available_qty=available_qty,
    )


def test_missing_attribute_is_unknown_not_inferred() -> None:
    left = _source(product_attributes={"battery_hours": 24})
    right = _source(product_attributes={})

    row = build_rows([left, right], ["battery_hours"])[0]

    assert row.cells[0].known is True
    assert row.cells[0].value == 24
    assert row.cells[0].unit == "hour"
    assert row.cells[0].display == "24 hour"

    assert row.cells[1].known is False
    assert row.cells[1].value is None
    assert row.cells[1].unit is None
    assert row.cells[1].display == "unknown"


def test_false_boolean_is_a_known_value() -> None:
    row = build_rows(
        [_source(product_attributes={"noise_cancelling": False})], ["noise_cancelling"]
    )[0]

    assert row.cells[0].known is True
    assert row.cells[0].value is False
    assert row.cells[0].display == "否"


def test_price_is_unknown_without_a_sellable_variant() -> None:
    row = build_rows([_source(price_cents=None, currency=None)], ["price"])[0]

    assert row.cells[0].known is False
    assert row.cells[0].unit is None
    assert row.cells[0].value is None
    assert row.cells[0].display == "unknown"


def test_price_display_keeps_integer_cents() -> None:
    row = build_rows([_source(price_cents=129900)], ["price"])[0]

    assert row.cells[0].value == 129900
    assert row.cells[0].unit == "CNY_cents"
    assert row.cells[0].display == "1299.00 CNY"


def test_stock_status_unknown_when_inventory_is_missing() -> None:
    known = build_rows([_source(available_qty=3)], ["stock_status"])[0]
    unknown = build_rows([_source(available_qty=None)], ["stock_status"])[0]

    assert known.cells[0].value == "in_stock"
    assert known.cells[0].display == "有货"
    assert unknown.cells[0].known is False
    assert unknown.cells[0].display == "unknown"


def test_variant_attribute_wins_over_product_attribute() -> None:
    row = build_rows(
        [_source(product_attributes={"color": "默认"}, variant_attributes={"color": "曜石黑"})],
        ["color"],
    )[0]

    assert row.cells[0].value == "曜石黑"


def test_rows_follow_requested_order_and_labels() -> None:
    rows = build_rows([_source(), _source()], ["category", "price", "brand"])

    assert [row.key for row in rows] == ["category", "price", "brand"]
    assert [row.label for row in rows] == ["类目", "价格", "品牌"]
    assert all(len(row.cells) == 2 for row in rows)


def test_empty_string_value_is_unknown() -> None:
    row = build_rows([_source(brand="")], ["brand"])[0]

    assert row.cells[0].known is False
    assert row.cells[0].display == "unknown"
