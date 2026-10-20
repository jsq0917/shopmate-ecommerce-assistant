"""Strict input/output schemas for the catalog tools.

``extra="forbid"`` means an unknown field is a validation error instead of being silently
dropped — a model cannot smuggle in ``shop_id``, ``user_id``, ``sql`` or a JSONB path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shopmate_ecommerce_assistant.domain.catalog.attributes import (
    DEFAULT_COMPARE_KEYS,
    MAX_COMPARE_PRODUCTS,
    MAX_SEARCH_ATTRIBUTES,
    MIN_COMPARE_PRODUCTS,
    normalize_attributes,
    normalize_compare_keys,
)

CONTRACT_VERSION = "1.0"
MAX_MONEY_CENTS = 100_000_000
MAX_SEARCH_LIMIT = 20
MAX_QUERY_CHARS = 200
MAX_NAME_CHARS = 80

StockStatusValue = Literal["in_stock", "out_of_stock", "unknown"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchProductsInput(_StrictModel):
    """Input of ``search_products`` (contract section 5.1)."""

    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    category: str | None = Field(default=None, max_length=MAX_NAME_CHARS)
    brand: str | None = Field(default=None, max_length=MAX_NAME_CHARS)
    budget_min_cents: int | None = Field(default=None, ge=0, le=MAX_MONEY_CENTS)
    budget_max_cents: int | None = Field(default=None, ge=0, le=MAX_MONEY_CENTS)
    attributes: dict[str, bool | int | float | str] | None = None
    in_stock_only: bool = False
    limit: int = Field(default=10, ge=1, le=MAX_SEARCH_LIMIT)

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("查询词不能为空")
        return stripped

    @field_validator("category", "brand")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("attributes")
    @classmethod
    def _normalize_attribute_filter(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        if len(value) > MAX_SEARCH_ATTRIBUTES:
            raise ValueError(f"属性过滤最多 {MAX_SEARCH_ATTRIBUTES} 项")
        return normalize_attributes(value)

    @model_validator(mode="after")
    def _budget_order(self) -> Self:
        if (
            self.budget_min_cents is not None
            and self.budget_max_cents is not None
            and self.budget_min_cents > self.budget_max_cents
        ):
            raise ValueError("预算下限不能大于上限")
        return self


class ProductCard(_StrictModel):
    """Structured product card rendered from PostgreSQL facts."""

    product_id: UUID
    variant_id: UUID
    title: str
    brand: str | None
    category: str
    sku: str
    price_cents: int
    currency: str
    stock_status: StockStatusValue
    available_qty: int | None
    attributes: dict[str, Any]
    matched_reasons: list[str]
    image_url: str | None = None
    is_synthetic: bool
    as_of: datetime


class SearchProductsData(_StrictModel):
    """Payload of a successful ``search_products`` call."""

    items: list[ProductCard]
    truncated: bool


class GetProductDetailInput(_StrictModel):
    """Input of ``get_product_detail``."""

    product_id: UUID
    variant_id: UUID | None = None


class VariantDetail(_StrictModel):
    """One SKU with its real price and stock summary."""

    id: UUID
    sku: str
    title: str
    attributes: dict[str, Any]
    price_cents: int
    currency: str
    status: str
    available_qty: int | None
    stock_status: StockStatusValue
    stock_updated_at: datetime | None


class ProductStockSummary(_StrictModel):
    """Product-level availability derived from the SKU rows."""

    available_qty: int | None
    stock_status: StockStatusValue
    updated_at: datetime | None


class ProductDetail(_StrictModel):
    """Product master data plus its SKUs."""

    id: UUID
    title: str
    description: str | None
    brand: str | None
    category: str
    attributes: dict[str, Any]
    status: str
    is_synthetic: bool
    image_url: str | None = None
    stock_summary: ProductStockSummary
    variants: list[VariantDetail]


class ProductDetailData(_StrictModel):
    """Payload of a successful ``get_product_detail`` call."""

    product: ProductDetail


class CompareProductsInput(_StrictModel):
    """Input of ``compare_products``; 2-4 unique product ids."""

    product_ids: list[UUID] = Field(
        min_length=MIN_COMPARE_PRODUCTS, max_length=MAX_COMPARE_PRODUCTS
    )
    attributes: list[str] = Field(default_factory=lambda: list(DEFAULT_COMPARE_KEYS))

    @field_validator("product_ids")
    @classmethod
    def _unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("商品 ID 不能重复")
        return value

    @model_validator(mode="after")
    def _normalize_keys(self) -> Self:
        # Normalizes both explicit keys and the default dimensions.
        self.attributes = list(normalize_compare_keys(self.attributes))
        return self


class CompareProductRef(_StrictModel):
    """Column header of the comparison table."""

    product_id: UUID
    title: str
    variant_id: UUID | None
    variant_title: str | None


class CompareValue(_StrictModel):
    """One aligned cell. ``known=false`` means "unknown", never a guessed value."""

    product_id: UUID
    known: bool
    value: bool | int | float | str | None
    unit: str | None
    display: str


class CompareRow(_StrictModel):
    """One comparison dimension across all compared products."""

    key: str
    label: str
    values: list[CompareValue]


class CompareProductsData(_StrictModel):
    """Payload of a successful ``compare_products`` call."""

    products: list[CompareProductRef]
    rows: list[CompareRow]


class CheckStockInput(_StrictModel):
    """Input of ``check_stock``."""

    variant_id: UUID
    quantity: int = Field(default=1, ge=1, le=999)


class WarehouseStockItem(_StrictModel):
    """Per-warehouse availability with its own timestamp."""

    warehouse_code: str
    available_qty: int
    updated_at: datetime | None


class CheckStockData(_StrictModel):
    """Payload of a successful ``check_stock`` call."""

    variant_id: UUID
    product_id: UUID
    sku: str
    requested_qty: int
    available_qty: int | None
    is_available: bool
    stock_status: StockStatusValue
    warehouses: list[WarehouseStockItem]


class ToolSuccess(_StrictModel):
    """Success envelope (contract section 3.1)."""

    ok: Literal[True] = True
    contract_version: str = CONTRACT_VERSION
    tool_call_id: UUID
    data: dict[str, Any]
    source: Literal["postgres"] = "postgres"
    as_of: datetime
    trace_id: UUID
    idempotent_replay: bool = False


class ToolFailure(_StrictModel):
    """Failure envelope (contract section 3.2); never contains internals."""

    ok: Literal[False] = False
    contract_version: str = CONTRACT_VERSION
    tool_call_id: UUID
    error_code: str
    user_message: str
    retryable: bool = False
    retry_after_ms: int | None = None
    trace_id: UUID


ToolResult = ToolSuccess | ToolFailure

__all__ = [
    "CONTRACT_VERSION",
    "CheckStockData",
    "CheckStockInput",
    "CompareProductRef",
    "CompareProductsData",
    "CompareProductsInput",
    "CompareRow",
    "CompareValue",
    "GetProductDetailInput",
    "ProductCard",
    "ProductDetail",
    "ProductDetailData",
    "ProductStockSummary",
    "SearchProductsData",
    "SearchProductsInput",
    "ToolFailure",
    "ToolResult",
    "ToolSuccess",
    "VariantDetail",
    "WarehouseStockItem",
]
