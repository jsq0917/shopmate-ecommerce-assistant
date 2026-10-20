"""Give the seeded synthetic accounts a demo password so the demo script can log in.

Stage 5 seeds shoppers, one support agent and one admin with the sentinel hash
``!synthetic-account-no-login``: the rows exist (so orders, shipments and knowledge metadata
stay referentially valid) but nobody can authenticate as them. This command keeps that
property by default and only opts the three demo accounts in, on explicit invocation.

Safety rails:

* only accounts whose e-mail domain is ``example.invalid`` **and** whose row is marked
  ``is_synthetic`` are touched;
* the password is never written to disk, only its Argon2 hash;
* repeated runs are no-ops (the existing hash is verified first).

Usage::

    uv run python scripts/demo_accounts.py --dry-run
    uv run python scripts/demo_accounts.py
    SHOPMATE_DEMO_PASSWORD='...' uv run python scripts/demo_accounts.py --json

The demo password is a synthetic credential for a demo shop. It is **not** a secret and must
never be reused for any real deployment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa

from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.core.security import hash_password, verify_password
from shopmate_ecommerce_assistant.db.models import Order, User
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory

DEMO_PASSWORD_ENV = "SHOPMATE_DEMO_PASSWORD"
DEFAULT_DEMO_PASSWORD = "ShopMate-Demo-Only-2026"
SYNTHETIC_DOMAIN = "example.invalid"
DEMO_ACCOUNTS: tuple[tuple[str, str], ...] = (
    ("shopper01@example.invalid", "shopper"),
    ("support01@example.invalid", "support"),
    ("admin01@example.invalid", "admin"),
)


@dataclass
class AccountResult:
    """Outcome for one demo account."""

    email: str
    role: str
    user_id: str | None
    action: str
    orders: list[dict[str, Any]]


def _recent_orders(rows: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "order_no": row.order_no,
            "status": row.status.value if hasattr(row.status, "value") else str(row.status),
            "total_cents": row.total_cents,
            "placed_at": row.placed_at.isoformat() if row.placed_at else None,
            "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
        }
        for row in rows
    ]


async def _run(password: str, dry_run: bool) -> list[AccountResult]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    results: list[AccountResult] = []
    try:
        async with factory() as session:
            for email, expected_role in DEMO_ACCOUNTS:
                user = (
                    await session.execute(
                        sa.select(User).where(
                            sa.func.lower(User.email_ci) == email,
                            User.is_synthetic.is_(True),
                        )
                    )
                ).scalar_one_or_none()
                if user is None:
                    results.append(
                        AccountResult(email, expected_role, None, "missing", [])
                    )
                    continue
                if not email.endswith(f"@{SYNTHETIC_DOMAIN}"):  # pragma: no cover - defensive
                    results.append(AccountResult(email, expected_role, str(user.id), "skipped", []))
                    continue

                role = user.role.value if hasattr(user.role, "value") else str(user.role)
                already = verify_password(password, user.password_hash)
                if already:
                    action = "unchanged"
                elif dry_run:
                    action = "would-set"
                else:
                    user.password_hash = hash_password(password)
                    action = "password-set"

                orders = (
                    (
                        await session.execute(
                            sa.select(Order)
                            .where(Order.user_id == user.id)
                            .order_by(Order.placed_at.desc())
                            .limit(5)
                        )
                    )
                    .scalars()
                    .all()
                )
                results.append(
                    AccountResult(email, role, str(user.id), action, _recent_orders(list(orders)))
                )
            if not dry_run:
                await session.commit()
    finally:
        await engine.dispose()
    return results


def _print_human(results: list[AccountResult], password: str | None) -> None:
    print("ShopMate 演示账号（合成数据，仅限本机/演示环境）")
    if password:
        print(f"  演示口令：{password}")
    print()
    for item in results:
        print(f"- {item.email}  role={item.role}  action={item.action}")
        if item.user_id:
            print(f"    user_id={item.user_id}")
        for order in item.orders:
            print(
                f"    订单 {order['order_no']} status={order['status']} "
                f"delivered_at={order['delivered_at']}"
            )
    print()
    print("提示：support01 / admin01 只能访问 demo 店铺数据；越权与转人工演示请使用不同账号。")


def main() -> int:
    parser = argparse.ArgumentParser(description="为合成演示账号设置演示口令")
    parser.add_argument("--dry-run", action="store_true", help="只报告将要修改的账号，不写库")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument(
        "--password",
        default=os.environ.get(DEMO_PASSWORD_ENV, DEFAULT_DEMO_PASSWORD),
        help=f"演示口令（默认读取 {DEMO_PASSWORD_ENV}，否则用内置演示口令）",
    )
    args = parser.parse_args()

    if len(args.password) < 8:
        print("演示口令至少 8 位。", file=sys.stderr)
        return 1

    try:
        results = asyncio.run(_run(args.password, args.dry_run))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"演示账号初始化失败：{exc}", file=sys.stderr)
        print(
            "请确认数据库已启动，且已执行 alembic upgrade head 与 scripts/seed.py。",
            file=sys.stderr,
        )
        return 1

    missing = [item.email for item in results if item.action == "missing"]
    if args.json:
        print(
            json.dumps(
                {
                    "password": None if args.dry_run else args.password,
                    "dry_run": args.dry_run,
                    "accounts": [
                        {
                            "email": item.email,
                            "role": item.role,
                            "user_id": item.user_id,
                            "action": item.action,
                            "orders": item.orders,
                        }
                        for item in results
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_human(results, args.password)

    if missing:
        print(f"未找到合成账号：{', '.join(missing)}；请先运行 scripts/seed.py。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
