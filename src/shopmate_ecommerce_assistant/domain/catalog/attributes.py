"""Controlled attribute vocabulary for search and comparison.

Anything that is not declared here is rejected with ``VALIDATION_ERROR``. This is what
prevents the model (or a crafted request) from inventing a parameter, filtering on an
arbitrary JSONB path, or making the comparison table grow a column that no product has.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class AttributeScope(StrEnum):
    """Where the value is stored: on ``products`` or on ``product_variants``."""

    PRODUCT = "product"
    VARIANT = "variant"


@dataclass(frozen=True, slots=True)
class AttributeSpec:
    """One comparable/searchable dimension with its display label and unit."""

    key: str
    label: str
    unit: str | None = None
    scope: AttributeScope = AttributeScope.PRODUCT


# Product-level attributes present in the synthetic catalog (stage 5).
_PRODUCT_ATTRIBUTES: tuple[AttributeSpec, ...] = (
    AttributeSpec("connectivity", "连接方式"),
    AttributeSpec("battery_hours", "续航", "hour"),
    AttributeSpec("noise_cancelling", "主动降噪"),
    AttributeSpec("weight_g", "重量", "g"),
    AttributeSpec("warranty_months", "保修期", "month"),
    AttributeSpec("layout", "配列"),
    AttributeSpec("switch", "轴体"),
    AttributeSpec("connection", "连接方式"),
    AttributeSpec("backlight", "背光"),
    AttributeSpec("dpi", "分辨率", "dpi"),
    AttributeSpec("battery_days", "续航", "day"),
    AttributeSpec("power_w", "功率", "W"),
    AttributeSpec("ports", "接口数量", "count"),
    AttributeSpec("protocol", "协议"),
    AttributeSpec("plug", "插头标准"),
    AttributeSpec("capacity_mah", "电池容量", "mAh"),
    AttributeSpec("screen_inch", "屏幕尺寸", "inch"),
    AttributeSpec("water_resistance", "防水等级"),
    AttributeSpec("gps", "定位"),
    AttributeSpec("resolution", "分辨率"),
    AttributeSpec("night_vision", "夜视"),
    AttributeSpec("storage", "存储方式"),
    AttributeSpec("material", "材质"),
    AttributeSpec("foldable", "可折叠"),
    AttributeSpec("magnetic", "磁吸"),
    AttributeSpec("length_m", "线长", "m"),
    AttributeSpec("connector", "接口类型"),
    AttributeSpec("waterproof", "防水等级"),
)

# Variant-level attributes. ``color`` differs per SKU, not per product.
_VARIANT_ATTRIBUTES: tuple[AttributeSpec, ...] = (
    AttributeSpec("color", "颜色", scope=AttributeScope.VARIANT),
)

# Dimensions read from columns rather than JSONB.
_DERIVED_ATTRIBUTES: tuple[AttributeSpec, ...] = (
    AttributeSpec("price", "价格", "CNY_cents"),
    AttributeSpec("brand", "品牌"),
    AttributeSpec("category", "类目"),
    AttributeSpec("stock_status", "库存状态"),
)

ATTRIBUTE_SPECS: dict[str, AttributeSpec] = {
    spec.key: spec for spec in (*_DERIVED_ATTRIBUTES, *_PRODUCT_ATTRIBUTES, *_VARIANT_ATTRIBUTES)
}

# Natural synonyms accepted from the router/model, mapped onto the stored key.
ATTRIBUTE_ALIASES: Mapping[str, str] = {
    "noise_cancellation": "noise_cancelling",
    "anc": "noise_cancelling",
    "battery_life_hours": "battery_hours",
    "weight": "weight_g",
    "warranty": "warranty_months",
    "color_name": "color",
}

DEFAULT_COMPARE_KEYS: tuple[str, ...] = ("price", "brand", "category", "stock_status")

MAX_SEARCH_ATTRIBUTES = 10
MAX_COMPARE_ATTRIBUTES = 20
MAX_COMPARE_PRODUCTS = 4
MIN_COMPARE_PRODUCTS = 2


def canonical_key(key: str) -> str:
    """Return the stored attribute key for ``key``.

    Raises:
        ValueError: when the key is not part of the controlled vocabulary.
    """
    normalized = key.strip().lower()
    normalized = ATTRIBUTE_ALIASES.get(normalized, normalized)
    if normalized not in ATTRIBUTE_SPECS:
        raise ValueError(f"不支持的属性：{key}")
    return normalized


def spec_for(key: str) -> AttributeSpec:
    """Return the specification for a canonical key."""
    return ATTRIBUTE_SPECS[canonical_key(key)]


def normalize_attributes(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize a search attribute filter.

    Only JSON scalars are accepted; nested objects/lists would require a query language
    and are therefore rejected instead of being reinterpreted.
    """
    if len(raw) > MAX_SEARCH_ATTRIBUTES:
        raise ValueError(f"属性过滤最多 {MAX_SEARCH_ATTRIBUTES} 项")

    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        canonical = canonical_key(key)
        if isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
            normalized[canonical] = value
        elif isinstance(value, str):
            normalized[canonical] = value
        else:
            raise ValueError(f"属性 {key} 的值必须是布尔、数字或字符串")
    return normalized


def normalize_compare_keys(keys: Iterable[str]) -> tuple[str, ...]:
    """Validate comparison keys, preserving request order and removing duplicates."""
    ordered: list[str] = []
    for key in keys:
        canonical = canonical_key(key)
        if canonical not in ordered:
            ordered.append(canonical)
    if not ordered:
        raise ValueError("至少指定一个比较维度")
    if len(ordered) > MAX_COMPARE_ATTRIBUTES:
        raise ValueError(f"比较维度最多 {MAX_COMPARE_ATTRIBUTES} 项")
    return tuple(ordered)


def split_search_attributes(
    attributes: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split normalized attributes into product-level and variant-level filters."""
    product_level: dict[str, Any] = {}
    variant_level: dict[str, Any] = {}
    for key, value in attributes.items():
        if key in {"price", "brand", "category", "stock_status"}:
            raise ValueError(f"属性 {key} 不是可过滤属性，请使用专用参数")
        spec = ATTRIBUTE_SPECS[key]
        if spec.scope is AttributeScope.VARIANT:
            variant_level[key] = value
        else:
            product_level[key] = value
    return product_level, variant_level


def compare_catalog() -> list[dict[str, str | None]]:
    """Expose the controlled vocabulary for docs, tests and future admin tooling."""
    return [
        {"key": spec.key, "label": spec.label, "unit": spec.unit, "scope": spec.scope.value}
        for spec in ATTRIBUTE_SPECS.values()
    ]
