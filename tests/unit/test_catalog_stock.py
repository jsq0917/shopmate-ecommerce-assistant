"""Unit tests for stock aggregation rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from shopmate_ecommerce_assistant.domain.catalog.models import VariantSnapshot
from shopmate_ecommerce_assistant.domain.catalog.stock import (
    aggregate_status,
    latest_stock_timestamp,
    stock_status,
    total_available,
)


def _variant(available_qty: int | None, *, hours: int = 0) -> VariantSnapshot:
    return VariantSnapshot(
        id=uuid4(),
        product_id=uuid4(),
        sku="SM-DEMO-01",
        title="示例 SKU",
        attributes={},
        price_cents=10000,
        currency="CNY",
        status="active",
        available_qty=available_qty,
        stock_updated_at=None
        if available_qty is None
        else datetime(2026, 10, 18, tzinfo=UTC) + timedelta(hours=hours),
    )


def test_stock_status_never_treats_missing_data_as_available() -> None:
    assert stock_status(None) == "unknown"
    assert stock_status(0) == "out_of_stock"
    assert stock_status(1) == "in_stock"


def test_total_available_sums_known_rows_only() -> None:
    assert total_available([_variant(3), _variant(None), _variant(4)]) == 7
    assert total_available([_variant(None)]) is None


def test_aggregate_status_is_conservative() -> None:
    assert aggregate_status([_variant(0), _variant(5)]) == "in_stock"
    assert aggregate_status([_variant(0), _variant(0)]) == "out_of_stock"
    assert aggregate_status([_variant(0), _variant(None)]) == "unknown"
    assert aggregate_status([]) == "unknown"


def test_latest_stock_timestamp_picks_newest() -> None:
    newest = latest_stock_timestamp([_variant(1), _variant(2, hours=5)])

    assert newest == datetime(2026, 10, 18, 5, tzinfo=UTC)
    assert latest_stock_timestamp([]) is None
