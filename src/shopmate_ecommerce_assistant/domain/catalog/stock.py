"""Stock status rules.

Availability is derived only from ``inventory.available_qty``. A missing inventory row is
``unknown`` — never assumed to be in stock, and never silently rendered as "0 available".
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from shopmate_ecommerce_assistant.domain.catalog.models import StockStatus, VariantSnapshot

IN_STOCK = "in_stock"
OUT_OF_STOCK = "out_of_stock"
UNKNOWN = "unknown"


def stock_status(available_qty: int | None) -> StockStatus:
    """Map an aggregated quantity to the public stock status."""
    if available_qty is None:
        return UNKNOWN
    if available_qty <= 0:
        return OUT_OF_STOCK
    return IN_STOCK


def total_available(variants: Iterable[VariantSnapshot]) -> int | None:
    """Sum known quantities; return ``None`` when nothing is known."""
    known = [variant.available_qty for variant in variants if variant.available_qty is not None]
    if not known:
        return None
    return sum(known)


def aggregate_status(variants: Sequence[VariantSnapshot]) -> StockStatus:
    """Status for a whole product.

    A product is ``in_stock`` when any known quantity is positive. It is
    ``out_of_stock`` only when every variant has a known quantity of zero; a partially
    known catalog stays ``unknown`` so we never overstate availability.
    """
    total = total_available(variants)
    if total is None:
        return UNKNOWN
    if total > 0:
        return IN_STOCK
    if any(variant.available_qty is None for variant in variants):
        return UNKNOWN
    return OUT_OF_STOCK


def latest_stock_timestamp(variants: Iterable[VariantSnapshot]) -> datetime | None:
    """Return the newest inventory timestamp across the given variants."""
    stamps = [
        variant.stock_updated_at for variant in variants if variant.stock_updated_at is not None
    ]
    if not stamps:
        return None
    return max(stamps)
