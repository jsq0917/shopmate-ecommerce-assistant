"""Create a demo-friendly order for ``shopper01`` (recently delivered, returnable).

Why this exists: the synthetic dataset's ``delivered`` orders are 1–120 days old, so most of
them are outside the 7-day return window. That makes the self-service return flow look
broken on a fresh demo. This command adds **one** deterministic order delivered two days
ago, plus one unpaid order, so "取消 / 支付 / 申请退货 / 申请退款" can all be demonstrated.

Safe to run repeatedly: rows are keyed by fixed ``order_no`` values and skipped when they
already exist. Nothing else in the database is touched.

Usage::

    uv run python scripts/demo_orders.py
    uv run python scripts/demo_orders.py --reset
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.core.config import get_settings
from shopmate_ecommerce_assistant.core.ids import stable_uuid
from shopmate_ecommerce_assistant.db.models import (
    Order,
    OrderItem,
    Product,
    ProductVariant,
    Shipment,
    ShipmentEvent,
    User,
)
from shopmate_ecommerce_assistant.db.models.enums import (
    OrderItemStatus,
    OrderStatus,
    ShipmentStatus,
)
from shopmate_ecommerce_assistant.db.session import create_engine, create_session_factory
from shopmate_ecommerce_assistant.domain.returns.rules import is_category_returnable
from shopmate_ecommerce_assistant.synthetic.catalog_data import shop_id

SHOPPER_EMAIL = "shopper01@example.invalid"
DELIVERED_ORDER_NO = "SM-2026-00901"
UNPAID_ORDER_NO = "SM-2026-00902"


async def _find_user(session: AsyncSession) -> User:
    user = (
        await session.execute(
            sa.select(User).where(User.shop_id == shop_id(), User.email_ci == SHOPPER_EMAIL)
        )
    ).scalar_one_or_none()
    if user is None:
        raise SystemExit("未找到 shopper01，请先运行 scripts/seed.py")
    return user


async def _variant(session: AsyncSession, sku: str) -> tuple[ProductVariant, Product]:
    row = (
        await session.execute(
            sa.select(ProductVariant, Product)
            .join(
                Product,
                sa.and_(
                    Product.id == ProductVariant.product_id,
                    Product.shop_id == ProductVariant.shop_id,
                ),
            )
            .where(ProductVariant.shop_id == shop_id(), ProductVariant.sku == sku)
        )
    ).first()
    if row is None:
        raise SystemExit(f"未找到 SKU {sku}，请先运行 scripts/seed.py")
    return row[0], row[1]


async def _ensure_order(
    session: AsyncSession,
    *,
    user: User,
    order_no: str,
    status: OrderStatus,
    placed_at: datetime,
    delivered_at: datetime | None,
    skus: list[str],
) -> Order:
    existing = (
        await session.execute(
            sa.select(Order).where(Order.shop_id == shop_id(), Order.order_no == order_no)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    order_id = stable_uuid("demo_order", order_no)
    items: list[OrderItem] = []
    total = 0
    for index, sku in enumerate(skus, start=1):
        variant, product = await _variant(session, sku)
        line_total = int(variant.price_cents)
        total += line_total
        items.append(
            OrderItem(
                id=stable_uuid("demo_order_item", order_no, str(index)),
                shop_id=shop_id(),
                order_id=order_id,
                variant_id=variant.id,
                sku_snapshot=variant.sku,
                title_snapshot=variant.title,
                category_snapshot=product.category,
                is_returnable_snapshot=is_category_returnable(product.category),
                quantity=1,
                unit_price_cents=int(variant.price_cents),
                line_total_cents=line_total,
                status=OrderItemStatus.ACTIVE,
                delivered_at=delivered_at,
            )
        )

    order = Order(
        id=order_id,
        shop_id=shop_id(),
        user_id=user.id,
        order_no=order_no,
        status=status,
        total_cents=total,
        currency="CNY",
        placed_at=placed_at,
        paid_at=None if status is OrderStatus.CREATED else placed_at + timedelta(minutes=3),
        delivered_at=delivered_at,
        shipping_address_masked="上海市 浦东新区 示例路 ** 号（合成地址）",
        source_system="mock_oms",
        is_synthetic=True,
    )
    session.add(order)
    session.add_all(items)

    if delivered_at is not None:
        shipped_at = placed_at + timedelta(hours=18)
        shipment_id = stable_uuid("demo_shipment", order_no)
        session.add(
            Shipment(
                id=shipment_id,
                shop_id=shop_id(),
                order_id=order_id,
                carrier="顺捷速运（合成）",
                tracking_no_masked="SF1000****0901",
                tracking_no_hash=stable_uuid("demo_tracking", order_no).bytes,
                status=ShipmentStatus.DELIVERED,
                shipped_at=shipped_at,
                estimated_delivery_at=shipped_at + timedelta(days=2),
                delivered_at=delivered_at,
                source_system="mock_oms",
                is_synthetic=True,
            )
        )
        timeline = [
            ("picked_up", "快件已由仓库揽收", shipped_at),
            ("in_transit", "快件已到达转运中心", shipped_at + timedelta(hours=8)),
            ("out_for_delivery", "快件正在派送中", delivered_at - timedelta(hours=3)),
            ("delivered", "快件已签收，感谢使用", delivered_at),
        ]
        for sequence, (code, description, occurred_at) in enumerate(timeline, start=1):
            session.add(
                ShipmentEvent(
                    id=stable_uuid("demo_shipment_event", order_no, str(sequence)),
                    shop_id=shop_id(),
                    shipment_id=shipment_id,
                    sequence_no=sequence,
                    status=ShipmentStatus(code),
                    description=description,
                    occurred_at=occurred_at,
                )
            )
    await session.flush()
    return order


async def _reset(session: AsyncSession) -> None:
    """Remove only the two demo orders created by this script."""
    order_ids = (
        await session.execute(
            sa.select(Order.id).where(
                Order.shop_id == shop_id(),
                Order.order_no.in_([DELIVERED_ORDER_NO, UNPAID_ORDER_NO]),
            )
        )
    ).scalars().all()
    if not order_ids:
        return
    shipment_ids = (
        await session.execute(
            sa.select(Shipment.id).where(
                Shipment.shop_id == shop_id(), Shipment.order_id.in_(order_ids)
            )
        )
    ).scalars().all()
    if shipment_ids:
        await session.execute(
            sa.delete(ShipmentEvent).where(ShipmentEvent.shipment_id.in_(shipment_ids))
        )
        await session.execute(sa.delete(Shipment).where(Shipment.id.in_(shipment_ids)))
    await session.execute(sa.delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
    await session.execute(sa.delete(Order).where(Order.id.in_(order_ids)))
    await session.commit()


async def main(reset: bool) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    now = datetime.now(UTC)
    async with factory() as session:
        if reset:
            await _reset(session)
            print("已删除演示订单")
        user = await _find_user(session)
        delivered = await _ensure_order(
            session,
            user=user,
            order_no=DELIVERED_ORDER_NO,
            status=OrderStatus.DELIVERED,
            placed_at=now - timedelta(days=4, hours=2),
            delivered_at=now - timedelta(days=2, hours=1),
            skus=["SM-QF-RF1-01", "SM-NJ-CUP500-01"],
        )
        unpaid = await _ensure_order(
            session,
            user=user,
            order_no=UNPAID_ORDER_NO,
            status=OrderStatus.CREATED,
            placed_at=now - timedelta(minutes=30),
            delivered_at=None,
            skus=["SM-QY-TB3-01"],
        )
        await session.commit()
        print(f"synthetic-account={user.email_ci}")
        print(
            f"delivered-order={delivered.order_no} status={delivered.status} "
            "2 天前签收，可直接演示退货"
        )
        print(f"unpaid-order={unpaid.order_no} status={unpaid.status} 可直接演示支付/取消")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="先删除再重建演示订单")
    args = parser.parse_args()
    asyncio.run(main(args.reset))
