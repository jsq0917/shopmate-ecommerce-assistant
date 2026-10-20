"""Read-only ports the catalog tools depend on.

The tool layer talks to this protocol, not to SQLAlchemy, which keeps the business rules
unit-testable with a fake reader while the real implementation lives in
``db/repositories/catalog.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from shopmate_ecommerce_assistant.domain.catalog.compare import CompareSource
from shopmate_ecommerce_assistant.domain.catalog.models import (
    ProductHit,
    ProductSnapshot,
    SearchCriteria,
    VariantSnapshot,
)


class CatalogReader(Protocol):
    """Shop-scoped catalog queries. Every call must be bound to ``shop_id``."""

    async def search(
        self, *, shop_id: UUID, criteria: SearchCriteria, limit: int
    ) -> list[ProductHit]:
        """Return at most ``limit`` products, cheapest matching SKU per product."""
        ...

    async def get_product(self, *, shop_id: UUID, product_id: UUID) -> ProductSnapshot | None:
        """Return one published product inside the shop, or ``None``."""
        ...

    async def list_variants(
        self, *, shop_id: UUID, product_id: UUID, variant_id: UUID | None = None
    ) -> list[VariantSnapshot]:
        """Return the product's SKUs with real prices and aggregated stock."""
        ...

    async def get_variant(self, *, shop_id: UUID, variant_id: UUID) -> VariantSnapshot | None:
        """Return one SKU with its warehouse-level stock rows."""
        ...

    async def load_compare_sources(
        self, *, shop_id: UUID, product_ids: Sequence[UUID]
    ) -> list[CompareSource]:
        """Return comparison sources in request order; missing products are omitted."""
        ...
