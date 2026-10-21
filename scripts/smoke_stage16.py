"""Stage-16 smoke check for the support workbench and admin reads.

Runs the **real** ASGI app (no containers started, no data written) against the local
development database, using tokens minted for the seeded synthetic accounts. Covers the
``docs/09-release-checklist.md`` §7 items that do not need a browser or BGE-M3:

* 7.12 conversation list for a shopper;
* 7.13 admin knowledge list;
* 7.14 support ticket queue (plus the negative cases: shopper 403, admin 403).

Usage::

    uv run python scripts/smoke_stage16.py
"""

from __future__ import annotations

import asyncio
import json
import sys

import httpx
import sqlalchemy as sa

from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.core.security import (
    AccessContext,
    issue_access_token,
    permissions_for,
)
from shopmate_ecommerce_assistant.db.models import Conversation, Shop, User, UserRole
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.main import create_app


async def _accounts(session) -> dict[str, tuple[object, object]]:
    rows = (
        await session.execute(
            sa.select(User.role, User.id, User.shop_id, Shop.name)
            .join(Shop, Shop.id == User.shop_id)
            .order_by(User.created_at)
        )
    ).all()
    found: dict[str, tuple[object, object]] = {}
    for role, user_id, shop_id, _shop_name in rows:
        key = str(role)
        if key not in found:
            found[key] = (user_id, shop_id)
    return found


async def main() -> int:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)

    try:
        async with factory() as session:
            accounts = await _accounts(session)
            conversation_id = await session.scalar(
                sa.select(Conversation.id).order_by(Conversation.created_at).limit(1)
            )
    except Exception as exc:  # noqa: BLE001 - a smoke script reports, it does not retry
        print(f"数据库不可用：{exc}")
        await engine.dispose()
        return 2

    missing = [role for role in ("shopper", "support", "admin") if role not in accounts]
    if missing:
        print(f"缺少种子账号角色：{missing}（先运行 scripts/seed.py）")
        await engine.dispose()
        return 2

    def token(role: str) -> str:
        user_id, shop_id = accounts[role]
        return issue_access_token(
            settings,
            AccessContext(
                shop_id=shop_id,
                user_id=user_id,
                role=UserRole(role),
                permissions=permissions_for(UserRole(role)),
            ),
        )

    def auth(role: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token(role)}"}

    app = create_app(settings)
    app.state.settings = settings
    app.state.session_factory = factory
    app.state.ingestion_runner = None
    transport = httpx.ASGITransport(app=app)

    failures: list[str] = []
    async with httpx.AsyncClient(transport=transport, base_url="http://smoke") as client:

        async def show(label: str, method: str, url: str, role: str, expect: int, **kw):
            response = await client.request(method, url, headers=auth(role), **kw)
            ok = response.status_code == expect
            detail = ""
            if response.headers.get("content-type", "").startswith("application/json"):
                body = response.json()
                if "data" in body and isinstance(body["data"], dict):
                    if "items" in body["data"]:
                        detail = f"items={len(body['data']['items'])}"
                    else:
                        detail = f"keys={len(body['data'])}"
                elif "error" in body:
                    detail = f"code={body['error']['code']}"
            print(
                f"{'PASS' if ok else 'FAIL'} {label}: {method} {url} as {role} "
                f"-> {response.status_code} (expect {expect}) {detail}"
            )
            if not ok:
                failures.append(f"{label} {response.status_code} != {expect}")

        # 7.12 / consumers keep their own conversation list
        await show("7.12 conversations", "GET", "/api/v1/conversations", "shopper", 200)
        # 7.13 / admin knowledge reads
        await show("7.13 admin documents", "GET", "/api/v1/admin/documents", "admin", 200)
        await show(
            "7.13 admin knowledge-bases", "GET", "/api/v1/admin/knowledge-bases", "admin", 200
        )
        # 7.14 / support workbench
        await show("7.14 support queue", "GET", "/api/v1/support/tickets", "support", 200)
        await show("7.14 shopper denied", "GET", "/api/v1/support/tickets", "shopper", 403)
        await show("7.14 admin denied", "GET", "/api/v1/support/tickets", "admin", 403)
        if conversation_id is not None:
            print(
                f"INFO 7.14 first conversation id = {conversation_id} "
                "(agent transcript requires an authorising ticket)"
            )
        # contract surface sanity: the support router really is registered
        openapi = (await client.get("/openapi.json")).json()
        support_paths = sorted(path for path in openapi["paths"] if "/support/" in path)
        print(f"INFO openapi support paths = {json.dumps(support_paths, ensure_ascii=False)}")
        if len(support_paths) != 4:
            failures.append(f"support paths {len(support_paths)} != 4")

    await engine.dispose()
    if failures:
        print(f"\n失败 {len(failures)} 项：" + "; ".join(failures))
        return 1
    print("\n全部通过：7.12 / 7.13 / 7.14（API 层，未含浏览器 UI）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
