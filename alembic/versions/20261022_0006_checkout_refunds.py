"""Stage 17: self-service checkout and refund applications.

Revision ID: 20261022_0006
Revises: 20261020_0005
Create Date: 2026-10-22

Additive only:

* ``orders.paid_at`` — when the simulated payment succeeded. Nullable, so every pre-existing
  synthetic order (seeded without a payment step) stays valid.
* ``refund_requests`` — one row per shopper application. Creation is a shopper action
  (``requested``); approval/rejection belongs to the support workbench. No money moves and
  no order amount is ever mutated here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261022_0006"
down_revision: str | None = "20261020_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REFUND_STATUS = ("requested", "approved", "rejected", "completed")
_REASON_CODES = (
    "SIZE_OR_FIT",
    "NO_LONGER_NEEDED",
    "DAMAGED_ON_ARRIVAL",
    "WRONG_ITEM",
    "QUALITY_ISSUE",
    "OTHER",
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.add_column("orders", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))

    refund_status = postgresql.ENUM(*_REFUND_STATUS, name="refund_status")
    refund_status.create(op.get_bind(), checkfirst=True)
    reason_code = postgresql.ENUM(*_REASON_CODES, name="return_reason_code", create_type=False)

    op.create_table(
        "refund_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_item_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("refund_no", sa.String(length=40), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False, server_default="order"),
        sa.Column(
            "status",
            postgresql.ENUM(*_REFUND_STATUS, name="refund_status", create_type=False),
            nullable=False,
            server_default="requested",
        ),
        sa.Column("reason_code", reason_code, nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("review_note", sa.String(length=500), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.CheckConstraint("amount_cents >= 0", name="ck_refunds_amount_non_negative"),
        sa.CheckConstraint("scope IN ('order', 'item')", name="ck_refunds_scope"),
        sa.ForeignKeyConstraint(
            ["shop_id", "order_id"],
            ["orders.shop_id", "orders.id"],
            name="fk_refunds_order_same_shop",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "user_id"],
            ["users.shop_id", "users.id"],
            name="fk_refunds_user_same_shop",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("shop_id", "refund_no", name="uq_refunds_shop_refund_no"),
        sa.Index("ix_refunds_shop_user_created", "shop_id", "user_id", "created_at"),
        sa.Index("ix_refunds_shop_status_created", "shop_id", "status", "created_at"),
        sa.Index("ix_refunds_order", "shop_id", "order_id"),
    )


def downgrade() -> None:
    op.drop_index("ix_refunds_order", table_name="refund_requests")
    op.drop_index("ix_refunds_shop_status_created", table_name="refund_requests")
    op.drop_index("ix_refunds_shop_user_created", table_name="refund_requests")
    op.drop_table("refund_requests")
    postgresql.ENUM(name="refund_status").drop(op.get_bind(), checkfirst=True)
    op.drop_column("orders", "paid_at")
