"""Field-aligned product comparison.

Rules enforced here:

* only whitelisted dimensions may become a row;
* a dimension that a product does not declare is ``known=false`` / ``value=null`` /
  ``display="unknown"`` — never inferred from a sibling product or from prose;
* numbers and money are copied verbatim from PostgreSQL, never recomputed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from shopmate_ecommerce_assistant.domain.catalog.attributes import ATTRIBUTE_SPECS
from shopmate_ecommerce_assistant.domain.catalog.stock import UNKNOWN, stock_status

KNOWN_DISPLAY = "unknown"


@dataclass(frozen=True, slots=True)
class CompareSource:
    """Everything the comparison needs for one product, already fetched by shop scope."""

    product_id: UUID
    title: str
    variant_id: UUID | None
    variant_title: str | None
    price_cents: int | None
    currency: str | None
    brand: str | None
    category: str | None
    product_attributes: Mapping[str, Any]
    variant_attributes: Mapping[str, Any]
    available_qty: int | None
    stock_updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CompareCell:
    """One cell of the comparison table."""

    product_id: UUID
    known: bool
    value: bool | int | float | str | None
    unit: str | None
    display: str


@dataclass(frozen=True, slots=True)
class CompareRow:
    """One aligned dimension across all compared products."""

    key: str
    label: str
    cells: tuple[CompareCell, ...]


def _lookup(source: CompareSource, key: str) -> tuple[bool, bool | int | float | str | None]:
    if key == "price":
        if source.price_cents is None:
            return False, None
        return True, source.price_cents
    if key == "brand":
        if not source.brand:
            return False, None
        return True, source.brand
    if key == "category":
        if not source.category:
            return False, None
        return True, source.category
    if key == "stock_status":
        status = stock_status(source.available_qty)
        if status == UNKNOWN:
            return False, None
        return True, status

    if key in source.variant_attributes and source.variant_attributes[key] is not None:
        return True, source.variant_attributes[key]
    if key in source.product_attributes and source.product_attributes[key] is not None:
        return True, source.product_attributes[key]
    return False, None


def _display(key: str, value: bool | int | float | str | None, unit: str | None) -> str:
    if value is None:
        return KNOWN_DISPLAY
    if isinstance(value, bool):
        return "是" if value else "否"
    if key == "price" and isinstance(value, int):
        currency = (unit or "CNY_cents").removesuffix("_cents")
        return f"{value // 100}.{value % 100:02d} {currency}"
    if key == "stock_status":
        return "有货" if value == "in_stock" else "缺货"
    if unit and isinstance(value, (int, float)):
        return f"{value} {unit}"
    return str(value)


def _unit_for(key: str, source: CompareSource) -> str | None:
    if key == "price":
        return f"{source.currency or 'CNY'}_cents"
    return ATTRIBUTE_SPECS[key].unit


def build_rows(sources: Sequence[CompareSource], keys: Sequence[str]) -> list[CompareRow]:
    """Build the aligned comparison table for the requested dimensions."""
    rows: list[CompareRow] = []
    for key in keys:
        spec = ATTRIBUTE_SPECS[key]
        cells: list[CompareCell] = []
        for source in sources:
            known, value = _lookup(source, key)
            unit = _unit_for(key, source) if known else None
            cells.append(
                CompareCell(
                    product_id=source.product_id,
                    known=known,
                    value=value if known else None,
                    unit=unit,
                    display=_display(key, value, unit) if known else KNOWN_DISPLAY,
                )
            )
        rows.append(CompareRow(key=key, label=spec.label, cells=tuple(cells)))
    return rows
