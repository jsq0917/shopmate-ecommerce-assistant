"""Plain data structures exchanged between the repository, domain and tool layers.

These dataclasses are deliberately framework-free: the repository fills them from
PostgreSQL rows, the domain layer reasons about them, and the tool layer renders them
into the public contract. No ORM object leaks past the repository boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

StockStatus = str  # "in_stock" | "out_of_stock" | "unknown"


@dataclass(frozen=True, slots=True)
class WarehouseStock:
    """One warehouse row, the atomic inventory fact."""

    warehouse_code: str
    available_qty: int
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class VariantSnapshot:
    """A sellable SKU with its PostgreSQL price and aggregated stock."""

    id: UUID
    product_id: UUID
    sku: str
    title: str
    attributes: Mapping[str, Any]
    price_cents: int
    currency: str
    status: str
    available_qty: int | None = None
    stock_updated_at: datetime | None = None
    warehouses: tuple[WarehouseStock, ...] = ()


@dataclass(frozen=True, slots=True)
class ProductSnapshot:
    """Product master data. It never carries a price or a stock number."""

    id: UUID
    title: str
    description: str | None
    brand: str | None
    category: str
    attributes: Mapping[str, Any]
    status: str
    is_synthetic: bool


@dataclass(frozen=True, slots=True)
class ProductHit:
    """A product paired with the cheapest variant that satisfied the filters."""

    product: ProductSnapshot
    variant: VariantSnapshot


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    """Validated, whitelist-only filters. Values are always bound as parameters."""

    tokens: tuple[str, ...] = ()
    category: str | None = None
    brand: str | None = None
    budget_min_cents: int | None = None
    budget_max_cents: int | None = None
    product_attributes: Mapping[str, Any] = field(default_factory=dict)
    variant_attributes: Mapping[str, Any] = field(default_factory=dict)
    in_stock_only: bool = False
