"""Parameterized, shop-scoped catalog queries.

Hard rules (see ``AGENTS.md`` sections 4 and 8.3):

* every statement filters on ``shop_id``; there is no query without tenant scope;
* values are always bound parameters — no string interpolation, no arbitrary SQL,
  no caller-supplied JSONB path;
* price and stock come from ``product_variants`` / ``inventory`` only;
* a missing inventory row yields ``None`` (unknown), never a fabricated ``0``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.db.models import (
    Inventory,
    Product,
    ProductStatus,
    ProductVariant,
    VariantStatus,
)
from shopmate_ecommerce_assistant.domain.catalog.compare import CompareSource
from shopmate_ecommerce_assistant.domain.catalog.models import (
    ProductHit,
    ProductSnapshot,
    SearchCriteria,
    VariantSnapshot,
    WarehouseStock,
)

_PUBLISHED_STATUSES = (ProductStatus.ACTIVE, ProductStatus.ARCHIVED)


def _like_pattern(value: str) -> str:
    """Escape LIKE wildcards so user text is matched literally."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _as_dict(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


class CatalogRepository:
    """SQLAlchemy implementation of :class:`CatalogReader`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _inventory_totals(self, shop_id: UUID) -> sa.Subquery:
        """Per-variant available quantity and its newest ``updated_at``."""
        return (
            sa.select(
                Inventory.variant_id.label("variant_id"),
                sa.func.sum(Inventory.available_qty).label("available_qty"),
                sa.func.max(Inventory.updated_at).label("stock_updated_at"),
            )
            .where(Inventory.shop_id == shop_id)
            .group_by(Inventory.variant_id)
            .subquery("inventory_totals")
        )

    async def search(
        self, *, shop_id: UUID, criteria: SearchCriteria, limit: int
    ) -> list[ProductHit]:
        """Return the cheapest matching SKU per matching product, ordered by price."""
        totals = self._inventory_totals(shop_id)

        columns = [
            Product.id.label("product_id"),
            Product.title.label("product_title"),
            Product.description.label("product_description"),
            Product.brand.label("product_brand"),
            Product.category.label("product_category"),
            Product.attributes_jsonb.label("product_attributes"),
            Product.status.label("product_status"),
            Product.is_synthetic.label("product_is_synthetic"),
            ProductVariant.id.label("variant_id"),
            ProductVariant.sku.label("variant_sku"),
            ProductVariant.title.label("variant_title"),
            ProductVariant.attributes_jsonb.label("variant_attributes"),
            ProductVariant.price_cents.label("price_cents"),
            ProductVariant.currency.label("currency"),
            ProductVariant.status.label("variant_status"),
            totals.c.available_qty.label("available_qty"),
            totals.c.stock_updated_at.label("stock_updated_at"),
        ]

        stmt = (
            sa.select(*columns)
            .join(
                ProductVariant,
                sa.and_(
                    ProductVariant.product_id == Product.id,
                    ProductVariant.shop_id == Product.shop_id,
                ),
            )
            .outerjoin(totals, totals.c.variant_id == ProductVariant.id)
            .where(
                Product.shop_id == shop_id,
                Product.deleted_at.is_(None),
                Product.status == ProductStatus.ACTIVE,
                ProductVariant.shop_id == shop_id,
                ProductVariant.deleted_at.is_(None),
                ProductVariant.status == VariantStatus.ACTIVE,
            )
        )

        if criteria.tokens:
            like_clauses = []
            for token in criteria.tokens:
                pattern = _like_pattern(token)
                like_clauses.extend(
                    (
                        Product.title.ilike(pattern, escape="\\"),
                        Product.brand.ilike(pattern, escape="\\"),
                        Product.category.ilike(pattern, escape="\\"),
                        Product.description.ilike(pattern, escape="\\"),
                        ProductVariant.title.ilike(pattern, escape="\\"),
                        ProductVariant.sku.ilike(pattern, escape="\\"),
                        sa.cast(Product.attributes_jsonb, sa.Text).ilike(pattern, escape="\\"),
                    )
                )
            stmt = stmt.where(sa.or_(*like_clauses))

        if criteria.category:
            stmt = stmt.where(Product.category.ilike(_like_pattern(criteria.category), escape="\\"))
        if criteria.brand:
            stmt = stmt.where(sa.func.lower(Product.brand) == criteria.brand.strip().lower())
        if criteria.budget_min_cents is not None:
            stmt = stmt.where(ProductVariant.price_cents >= criteria.budget_min_cents)
        if criteria.budget_max_cents is not None:
            stmt = stmt.where(ProductVariant.price_cents <= criteria.budget_max_cents)
        if criteria.product_attributes:
            stmt = stmt.where(Product.attributes_jsonb.contains(dict(criteria.product_attributes)))
        if criteria.variant_attributes:
            stmt = stmt.where(
                ProductVariant.attributes_jsonb.contains(dict(criteria.variant_attributes))
            )
        if criteria.in_stock_only:
            stmt = stmt.where(sa.func.coalesce(totals.c.available_qty, 0) > 0)

        ranked = stmt.add_columns(
            sa.func.row_number()
            .over(
                partition_by=ProductVariant.product_id,
                order_by=(ProductVariant.price_cents, ProductVariant.id),
            )
            .label("variant_rank")
        ).subquery("ranked_variants")
        final = (
            sa.select(ranked)
            .where(ranked.c.variant_rank == 1)
            .order_by(
                ranked.c.price_cents,
                ranked.c.product_title,
                ranked.c.product_id,
            )
            .limit(limit)
        )

        rows = (await self._session.execute(final)).mappings().all()
        return [self._hit_from_row(row) for row in rows]

    async def get_product(self, *, shop_id: UUID, product_id: UUID) -> ProductSnapshot | None:
        """Return one published product scoped to the shop."""
        stmt = sa.select(
            Product.id,
            Product.title,
            Product.description,
            Product.brand,
            Product.category,
            Product.attributes_jsonb,
            Product.status,
            Product.is_synthetic,
        ).where(
            Product.shop_id == shop_id,
            Product.id == product_id,
            Product.deleted_at.is_(None),
            Product.status.in_(_PUBLISHED_STATUSES),
        )
        row = (await self._session.execute(stmt)).mappings().first()
        return None if row is None else self._product_from_row(row)

    async def list_variants(
        self, *, shop_id: UUID, product_id: UUID, variant_id: UUID | None = None
    ) -> list[VariantSnapshot]:
        """Return all non-deleted SKUs of a product with real price and stock totals."""
        totals = self._inventory_totals(shop_id)
        stmt = (
            sa.select(
                ProductVariant.id,
                ProductVariant.product_id,
                ProductVariant.sku,
                ProductVariant.title,
                ProductVariant.attributes_jsonb,
                ProductVariant.price_cents,
                ProductVariant.currency,
                ProductVariant.status,
                totals.c.available_qty,
                totals.c.stock_updated_at,
            )
            .outerjoin(totals, totals.c.variant_id == ProductVariant.id)
            .where(
                ProductVariant.shop_id == shop_id,
                ProductVariant.product_id == product_id,
                ProductVariant.deleted_at.is_(None),
            )
            .order_by(ProductVariant.price_cents, ProductVariant.sku)
        )
        if variant_id is not None:
            stmt = stmt.where(ProductVariant.id == variant_id)

        rows = (await self._session.execute(stmt)).mappings().all()
        return [self._variant_from_row(row) for row in rows]

    async def get_variant(self, *, shop_id: UUID, variant_id: UUID) -> VariantSnapshot | None:
        """Return one SKU, including its per-warehouse stock rows."""
        totals = self._inventory_totals(shop_id)
        stmt = (
            sa.select(
                ProductVariant.id,
                ProductVariant.product_id,
                ProductVariant.sku,
                ProductVariant.title,
                ProductVariant.attributes_jsonb,
                ProductVariant.price_cents,
                ProductVariant.currency,
                ProductVariant.status,
                totals.c.available_qty,
                totals.c.stock_updated_at,
            )
            .outerjoin(totals, totals.c.variant_id == ProductVariant.id)
            .where(
                ProductVariant.shop_id == shop_id,
                ProductVariant.id == variant_id,
                ProductVariant.deleted_at.is_(None),
            )
        )
        row = (await self._session.execute(stmt)).mappings().first()
        if row is None:
            return None

        warehouses = await self.list_warehouses(shop_id=shop_id, variant_id=variant_id)
        return self._variant_from_row(row, warehouses=warehouses)

    async def list_warehouses(
        self, *, shop_id: UUID, variant_id: UUID
    ) -> tuple[WarehouseStock, ...]:
        """Return the warehouse rows that make up a variant's availability."""
        stmt = (
            sa.select(
                Inventory.warehouse_code,
                Inventory.available_qty,
                Inventory.updated_at,
            )
            .where(Inventory.shop_id == shop_id, Inventory.variant_id == variant_id)
            .order_by(Inventory.warehouse_code)
        )
        rows = (await self._session.execute(stmt)).mappings().all()
        return tuple(
            WarehouseStock(
                warehouse_code=row["warehouse_code"],
                available_qty=int(row["available_qty"]),
                updated_at=row["updated_at"],
            )
            for row in rows
        )

    async def load_compare_sources(
        self, *, shop_id: UUID, product_ids: Sequence[UUID]
    ) -> list[CompareSource]:
        """Load products and their cheapest active SKU, preserving request order."""
        if not product_ids:
            return []

        product_stmt = sa.select(
            Product.id,
            Product.title,
            Product.description,
            Product.brand,
            Product.category,
            Product.attributes_jsonb,
            Product.status,
            Product.is_synthetic,
        ).where(
            Product.shop_id == shop_id,
            Product.id.in_(tuple(product_ids)),
            Product.deleted_at.is_(None),
            Product.status == ProductStatus.ACTIVE,
        )
        product_rows = (await self._session.execute(product_stmt)).mappings().all()
        products = {row["id"]: self._product_from_row(row) for row in product_rows}
        if not products:
            return []

        totals = self._inventory_totals(shop_id)
        variant_stmt = (
            sa.select(
                ProductVariant.id,
                ProductVariant.product_id,
                ProductVariant.sku,
                ProductVariant.title,
                ProductVariant.attributes_jsonb,
                ProductVariant.price_cents,
                ProductVariant.currency,
                ProductVariant.status,
                totals.c.available_qty,
                totals.c.stock_updated_at,
                sa.func.row_number()
                .over(
                    partition_by=ProductVariant.product_id,
                    order_by=(ProductVariant.price_cents, ProductVariant.id),
                )
                .label("variant_rank"),
            )
            .outerjoin(totals, totals.c.variant_id == ProductVariant.id)
            .where(
                ProductVariant.shop_id == shop_id,
                ProductVariant.product_id.in_(tuple(products)),
                ProductVariant.deleted_at.is_(None),
                ProductVariant.status == VariantStatus.ACTIVE,
            )
            .subquery("ranked_variants")
        )
        variant_rows = (
            (
                await self._session.execute(
                    sa.select(variant_stmt).where(variant_stmt.c.variant_rank == 1)
                )
            )
            .mappings()
            .all()
        )
        variants = {row["product_id"]: self._variant_from_row(row) for row in variant_rows}

        sources: list[CompareSource] = []
        for product_id in product_ids:
            product = products.get(product_id)
            if product is None:
                continue
            variant = variants.get(product_id)
            sources.append(
                CompareSource(
                    product_id=product.id,
                    title=product.title,
                    variant_id=None if variant is None else variant.id,
                    variant_title=None if variant is None else variant.title,
                    price_cents=None if variant is None else variant.price_cents,
                    currency=None if variant is None else variant.currency,
                    brand=product.brand,
                    category=product.category,
                    product_attributes=product.attributes,
                    variant_attributes={} if variant is None else variant.attributes,
                    available_qty=None if variant is None else variant.available_qty,
                    stock_updated_at=None if variant is None else variant.stock_updated_at,
                )
            )
        return sources

    @staticmethod
    def _product_from_row(row: Mapping[str, Any]) -> ProductSnapshot:
        return ProductSnapshot(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            brand=row["brand"],
            category=row["category"],
            attributes=_as_dict(row["attributes_jsonb"]),
            status=str(row["status"]),
            is_synthetic=bool(row["is_synthetic"]),
        )

    @staticmethod
    def _variant_from_row(
        row: Mapping[str, Any], *, warehouses: tuple[WarehouseStock, ...] = ()
    ) -> VariantSnapshot:
        quantity = row["available_qty"]
        stamp: datetime | None = row["stock_updated_at"]
        return VariantSnapshot(
            id=row["id"],
            product_id=row["product_id"],
            sku=row["sku"],
            title=row["title"],
            attributes=_as_dict(row["attributes_jsonb"]),
            price_cents=int(row["price_cents"]),
            currency=str(row["currency"]),
            status=str(row["status"]),
            available_qty=None if quantity is None else int(quantity),
            stock_updated_at=stamp,
            warehouses=warehouses,
        )

    @classmethod
    def _hit_from_row(cls, row: Mapping[str, Any]) -> ProductHit:
        product = ProductSnapshot(
            id=row["product_id"],
            title=row["product_title"],
            description=row["product_description"],
            brand=row["product_brand"],
            category=row["product_category"],
            attributes=_as_dict(row["product_attributes"]),
            status=str(row["product_status"]),
            is_synthetic=bool(row["product_is_synthetic"]),
        )
        variant_row = {
            "id": row["variant_id"],
            "product_id": row["product_id"],
            "sku": row["variant_sku"],
            "title": row["variant_title"],
            "attributes_jsonb": row["variant_attributes"],
            "price_cents": row["price_cents"],
            "currency": row["currency"],
            "status": row["variant_status"],
            "available_qty": row["available_qty"],
            "stock_updated_at": row["stock_updated_at"],
        }
        return ProductHit(product=product, variant=cls._variant_from_row(variant_row))
