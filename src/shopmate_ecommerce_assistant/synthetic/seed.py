"""Idempotent seeding of synthetic commerce data and knowledge source files."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.core import paths
from shopmate_ecommerce_assistant.db.models import (
    Inventory,
    Order,
    OrderItem,
    Product,
    ProductVariant,
    Promotion,
    Shipment,
    ShipmentEvent,
    Shop,
    User,
)
from shopmate_ecommerce_assistant.synthetic.catalog_data import Dataset, build_dataset
from shopmate_ecommerce_assistant.synthetic.knowledge_corpus import POLICY_DOCS
from shopmate_ecommerce_assistant.synthetic.writers import (
    dataset_fingerprint,
    render_all,
    write_catalog_snapshot,
    write_eval_cases,
    write_faq,
    write_manifest,
)

logger = logging.getLogger(__name__)

TABLE_MODELS: tuple[tuple[type[Any], tuple[str, ...]], ...] = (
    (Shop, ("id",)),
    (User, ("id",)),
    (Product, ("id",)),
    (ProductVariant, ("id",)),
    (Inventory, ("shop_id", "variant_id", "warehouse_code")),
    (Promotion, ("id",)),
    (Order, ("id",)),
    (OrderItem, ("id",)),
    (Shipment, ("id",)),
    (ShipmentEvent, ("shop_id", "shipment_id", "sequence_no")),
)


@dataclass(slots=True)
class SeedReport:
    """Summary of a seed run, used by the CLI and tests."""

    counts: dict[str, int] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    fingerprint: str = ""
    manifest_documents: int = 0
    faq_entries: int = 0
    eval_cases: int = 0


def _clean(model: type[Any], row: dict[str, Any]) -> dict[str, Any]:
    columns = set(model.__table__.columns.keys())
    return {key: value for key, value in row.items() if key in columns}


async def _upsert(
    session: AsyncSession,
    model: type[Any],
    rows: list[dict[str, Any]],
    conflict_columns: tuple[str, ...],
) -> int:
    if not rows:
        return 0
    cleaned = [_clean(model, row) for row in rows]
    stmt = postgresql.insert(model).values(cleaned)
    excluded = stmt.excluded
    skip = set(conflict_columns) | {"id", "created_at"}
    update_columns = {
        column: getattr(excluded, column) for column in cleaned[0] if column not in skip
    }
    if "updated_at" in model.__table__.columns:
        update_columns["updated_at"] = sa.func.now()
    if update_columns:
        stmt = stmt.on_conflict_do_update(
            index_elements=list(conflict_columns), set_=update_columns
        )
    else:  # pragma: no cover - every table has mutable columns
        stmt = stmt.on_conflict_do_nothing(index_elements=list(conflict_columns))
    await session.execute(stmt)
    return len(cleaned)


async def _row_counts(session: AsyncSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model, _ in TABLE_MODELS:
        total = await session.scalar(sa.select(sa.func.count()).select_from(model))
        counts[model.__table__.name] = int(total or 0)
    return counts


def write_source_files() -> tuple[list[str], int, int, int]:
    """Render knowledge files, manifest, FAQ and evaluation data.

    Returns:
        (written files, manifest documents, faq entries, eval cases)
    """
    written: list[Path] = render_all(POLICY_DOCS, paths.KNOWLEDGE_DIR)
    manifest_documents = write_manifest(paths.MANIFEST_PATH)
    faq_entries = write_faq(paths.FAQ_PATH)
    eval_cases = write_eval_cases(paths.EVAL_QUESTIONS_PATH)
    dataset = build_dataset()
    write_catalog_snapshot(dataset, paths.SYNTHETIC_DIR / "catalog_snapshot.md")
    written.extend([paths.MANIFEST_PATH, paths.FAQ_PATH, paths.EVAL_QUESTIONS_PATH])
    return (
        [path.relative_to(paths.PROJECT_ROOT).as_posix() for path in written],
        manifest_documents,
        faq_entries,
        eval_cases,
    )


async def seed_database(session: AsyncSession, dataset: Dataset) -> dict[str, int]:
    """Upsert every synthetic row; safe to run repeatedly."""
    await _upsert(session, Shop, [dataset.shop], ("id",))
    await _upsert(session, User, dataset.users, ("id",))
    await _upsert(session, Product, dataset.products, ("id",))
    await _upsert(session, ProductVariant, dataset.variants, ("id",))
    await _upsert(
        session, Inventory, dataset.inventory, ("shop_id", "variant_id", "warehouse_code")
    )
    await _upsert(session, Promotion, dataset.promotions, ("id",))
    await _upsert(session, Order, dataset.orders, ("id",))
    await _upsert(session, OrderItem, dataset.order_items, ("id",))
    await _upsert(session, Shipment, dataset.shipments, ("id",))
    await _upsert(
        session, ShipmentEvent, dataset.shipment_events, ("shop_id", "shipment_id", "sequence_no")
    )
    await session.commit()
    return await _row_counts(session)


async def run_seed(session: AsyncSession) -> SeedReport:
    """Seed files and database rows, returning a reproducibility report."""
    dataset = build_dataset()
    counts = await seed_database(session, dataset)
    files, manifest_documents, faq_entries, eval_cases = write_source_files()
    return SeedReport(
        counts=counts,
        files=files,
        fingerprint=dataset_fingerprint(dataset),
        manifest_documents=manifest_documents,
        faq_entries=faq_entries,
        eval_cases=eval_cases,
    )
