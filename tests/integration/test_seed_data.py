"""Synthetic seed tests: counts, synthetic flags, no PII and idempotency."""

from __future__ import annotations

import json
import re

import pytest
import sqlalchemy as sa

from shopmate_ecommerce_assistant.core import paths
from shopmate_ecommerce_assistant.core.security import hash_password
from shopmate_ecommerce_assistant.db.models import Inventory, Order, Product, Shop, User
from shopmate_ecommerce_assistant.synthetic.knowledge_corpus import (
    POLICY_DOCS,
    faq_records,
    manifest_payload,
)
from shopmate_ecommerce_assistant.synthetic.seed import run_seed

pytestmark = pytest.mark.integration

PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")


async def test_run_seed_preserves_an_installed_demo_password(session) -> None:
    """A re-seed must not reset the demo credential to the no-login sentinel.

    Seeding only ever writes ``!synthetic-account-no-login``; the real demo password is
    installed afterwards by ``scripts/demo_accounts.py``. Without the
    ``PRESERVE_ON_CONFLICT`` guard, every full test suite run re-seeded the shared demo
    database and silently broke demo login (found 2026-10-24).
    """
    await run_seed(session)

    installed = hash_password("ShopMate-Demo-Only-2026")
    await session.execute(
        sa.update(User).where(User.email_ci == "shopper01@example.invalid").values(
            password_hash=installed
        )
    )
    await session.commit()

    await run_seed(session)

    stored = await session.scalar(
        sa.select(User.password_hash).where(User.email_ci == "shopper01@example.invalid")
    )
    assert stored == installed, "re-seed must not overwrite an installed demo password"


async def test_seed_counts_metadata_and_idempotency(session) -> None:
    first = await run_seed(session)
    second = await run_seed(session)

    assert first.counts == second.counts, "重复执行 seed 不应改变行数"
    assert first.fingerprint == second.fingerprint

    assert first.counts["shops"] == 1
    assert first.counts["products"] >= 30
    assert first.counts["product_variants"] >= 30
    # ``run_seed`` reports the rows it owns. The table may also contain legitimate
    # non-seed rows (e.g. the Playwright fixture's synthetic order), which must not be
    # mistaken for seed output — see the scoped assertion below.
    assert first.counts["orders"] >= 100
    assert first.counts["order_items"] >= 100
    assert first.counts["promotions"] == 4

    # Seed owns SM-2026-00001 … SM-2026-00100. Storefront orders and the demo helper use
    # higher numbers, so the assertion is "the seed range is complete", not "the table has
    # exactly 100 rows".
    seed_numbers = {f"SM-2026-{index:05d}" for index in range(1, 101)}
    order_numbers = await session.scalars(
        sa.select(Order.order_no).where(Order.order_no.like("SM-2026-%"))
    )
    present_orders = set(order_numbers.all())
    assert seed_numbers <= present_orders, "种子必须覆盖 SM-2026-00001…00100"

    unique_documents = {doc.key for doc in POLICY_DOCS}
    assert len(unique_documents) >= 20, "至少 20 份政策文档"
    assert first.manifest_documents == len(POLICY_DOCS)
    assert first.faq_entries == 50
    # ``run_seed`` no longer rewrites an existing eval dataset (stage 13 extended it to
    # 136 curated cases), so the report reflects what is on disk: at least the seeded 100.
    assert first.eval_cases >= 100


async def test_every_seeded_row_is_marked_synthetic(session) -> None:
    await run_seed(session)

    for model in (Shop, User, Product, Inventory, Order):
        column = model.__table__.columns.get("is_synthetic")
        assert column is not None, f"{model.__tablename__} 缺少 is_synthetic 列"
        total = await session.scalar(sa.select(sa.func.count()).select_from(model))
        synthetic = await session.scalar(
            sa.select(sa.func.count()).select_from(model).where(column.is_(True))
        )
        assert total == synthetic, f"{model.__tablename__} 存在未标记 synthetic 的行"


async def test_seeded_users_use_reserved_domains_only(session) -> None:
    await run_seed(session)

    emails = (
        await session.scalars(
            sa.select(User.email_ci).where(User.password_hash.like("!synthetic%"))
        )
    ).all()

    assert emails
    assert all(email.endswith(".invalid") for email in emails)


async def test_seeded_orders_have_unique_numbers_and_consistent_states(session) -> None:
    await run_seed(session)

    order_numbers = (await session.scalars(sa.select(Order.order_no))).all()
    # Uniqueness is a table-wide invariant; the exact range is a seed-owned invariant.
    assert len(order_numbers) == len(set(order_numbers))
    seed_numbers = {f"SM-2026-{index:05d}" for index in range(1, 101)}
    assert seed_numbers <= set(order_numbers)

    delivered_without_timestamp = await session.scalar(
        sa.select(sa.func.count())
        .select_from(Order)
        .where(Order.status.in_(("delivered", "completed")), Order.delivered_at.is_(None))
    )
    assert delivered_without_timestamp == 0

    # Address hygiene is asserted on seed-owned rows: the seed contract is "every seeded
    # address is a synthetic, PII-free masked value". Other synthetic writers (the
    # Playwright fixture) keep their own addresses and are not seed output.
    addresses = (
        await session.scalars(
            sa.select(Order.shipping_address_masked).where(
                Order.order_no.like("SM-2026-%"), Order.source_system == "mock_oms"
            )
        )
    ).all()
    assert len(addresses) >= 100
    assert all("合成" in address for address in addresses)
    assert not any(PHONE_PATTERN.search(address or "") for address in addresses)


def test_faq_and_eval_datasets_are_complete_and_unique() -> None:
    faq = faq_records()
    assert len(faq) == 50
    assert len({row["id"] for row in faq}) == 50
    assert all(row["is_synthetic"] for row in faq)

    cases = [json.loads(line) for line in paths.EVAL_QUESTIONS_PATH.read_text("utf-8").splitlines()]
    # The seeded baseline is 100 rows, but the file is a curated artefact: stage 13 added
    # 36 cases (authorization / multi-turn / short query / no answer). The seed must not
    # truncate it, so the assertion is "at least the seeded 100", plus uniqueness/coverage.
    assert len(cases) >= 100
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(case["is_synthetic"] for case in cases)
    assert {
        "product_discovery",
        "product_compare",
        "product_fact",
        "policy_faq",
        "order_status",
        "shipment",
        "return_eligibility",
        "return_request",
        "complaint_handoff",
        "smalltalk_or_unknown",
    } <= {case["expected_intent"] for case in cases}


def test_manifest_matches_declared_policy_documents() -> None:
    payload = manifest_payload()

    assert payload["shop_key"] == "demo"
    entries = payload["documents"]
    assert len(entries) == len(POLICY_DOCS)
    assert {entry["document_key"] for entry in entries} == {doc.key for doc in POLICY_DOCS}
    assert all(entry["effective_from"] for entry in entries)
    assert all(entry["knowledge_base"] for entry in entries)


def test_generated_policy_files_exist_on_disk() -> None:
    payload = manifest_payload()

    for entry in payload["documents"]:
        target = paths.KNOWLEDGE_DIR / entry["file"]
        assert target.is_file(), target
        assert target.stat().st_size > 200, target
