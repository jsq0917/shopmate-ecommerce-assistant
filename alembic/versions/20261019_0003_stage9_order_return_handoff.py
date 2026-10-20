"""Stage 9: conversations, tool audit, returns and handoff.

Revision ID: 20261019_0003
Revises: 20261019_0002
Create Date: 2026-10-19

The tables added here are the only write paths a chat tool can reach. Nothing in this
migration stores a refund decision: ``return_requests`` holds applications, and the
``uq_return_active_item`` partial index is what makes "one active application per order
item" true even under concurrent retries.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261019_0003"
down_revision: str | None = "20261019_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "return_status": (
        "draft",
        "submitted",
        "under_review",
        "approved",
        "completed",
        "rejected",
        "cancelled",
    ),
    "return_reason_code": (
        "SIZE_OR_FIT",
        "NO_LONGER_NEEDED",
        "DAMAGED_ON_ARRIVAL",
        "WRONG_ITEM",
        "QUALITY_ISSUE",
        "OTHER",
    ),
    "risk_level": ("low", "medium", "high", "critical"),
    "handoff_status": ("open", "assigned", "resolved", "closed"),
    "tool_call_status": ("started", "succeeded", "failed"),
    "idempotency_status": ("processing", "succeeded", "failed"),
}


def _enum(name: str) -> postgresql.ENUM:
    """Return a reference to an enum type created by :func:`upgrade`."""
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


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
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id", "user_id"],
            ["users.shop_id", "users.id"],
            name="fk_conversations_user_same_shop",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("shop_id", "id", "user_id", name="uq_conversations_shop_id_user_id"),
    )
    op.create_index(
        "ix_conversations_shop_user_updated",
        "conversations",
        ["shop_id", "user_id", "updated_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("trace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column(
            "input_redacted_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "result_summary_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", _enum("tool_call_status"), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("latency_ms >= 0", name="ck_tool_calls_latency_non_negative"),
    )
    op.create_index(
        "ix_tool_calls_conversation_created",
        "tool_calls",
        ["shop_id", "conversation_id", "created_at"],
    )
    op.create_index(
        "ix_tool_calls_tool_status",
        "tool_calls",
        ["shop_id", "tool_name", "status", "created_at"],
    )
    op.create_index(
        "uq_tool_calls_idempotency",
        "tool_calls",
        ["shop_id", "actor_user_id", "tool_name", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.LargeBinary, nullable=False),
        sa.Column("status", _enum("idempotency_status"), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "response_snapshot_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint(
            "shop_id",
            "actor_user_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_scope",
        ),
    )
    op.create_index("ix_idempotency_expires", "idempotency_records", ["expires_at"])

    op.create_table(
        "return_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_item_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("reason_code", _enum("return_reason_code"), nullable=False),
        sa.Column("status", _enum("return_status"), nullable=False, server_default="submitted"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.String(240), nullable=True),
        sa.Column(
            "required_materials_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id", "order_id", "user_id"],
            ["orders.shop_id", "orders.id", "orders.user_id"],
            name="fk_return_requests_order_same_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id", "order_item_id", "order_id"],
            ["order_items.shop_id", "order_items.id", "order_items.order_id"],
            name="fk_return_requests_item_same_order",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_return_requests_order", "return_requests", ["shop_id", "order_id"])
    op.create_index(
        "ix_return_requests_user", "return_requests", ["shop_id", "user_id", "created_at"]
    )
    op.create_index(
        "uq_return_active_item",
        "return_requests",
        ["shop_id", "order_item_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('submitted', 'under_review', 'approved')"),
    )

    op.create_table(
        "handoff_tickets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("risk_level", _enum("risk_level"), nullable=False),
        sa.Column("primary_reason_code", sa.String(80), nullable=False),
        sa.Column(
            "risk_rule_codes_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("summary_redacted", sa.Text, nullable=False),
        sa.Column("status", _enum("handoff_status"), nullable=False, server_default="open"),
        sa.Column("priority", sa.Integer, nullable=False),
        sa.Column("assigned_to", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id", "conversation_id", "user_id"],
            ["conversations.shop_id", "conversations.id", "conversations.user_id"],
            name="fk_handoff_tickets_conversation_same_user",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("priority BETWEEN 1 AND 5", name="ck_handoff_priority_range"),
    )
    op.create_index(
        "ix_handoff_queue", "handoff_tickets", ["shop_id", "status", "risk_level", "created_at"]
    )
    op.create_index("ix_handoff_user", "handoff_tickets", ["shop_id", "user_id", "created_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.String(20), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("request_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("trace_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("risk_level", _enum("risk_level"), nullable=True),
        sa.Column(
            "metadata_redacted_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_audit_shop_time", "audit_events", ["shop_id", "occurred_at"])
    op.create_index("ix_audit_request", "audit_events", ["request_id", "trace_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("handoff_tickets")
    op.drop_table("return_requests")
    op.drop_table("idempotency_records")
    op.drop_table("tool_calls")
    op.drop_table("conversations")

    bind = op.get_bind()
    for name in reversed(list(ENUMS)):
        postgresql.ENUM(*ENUMS[name], name=name).drop(bind, checkfirst=True)
