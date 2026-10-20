"""Stage 10: chat messages, refresh sessions and evaluation runs.

Revision ID: 20261019_0004
Revises: 20261019_0003
Create Date: 2026-10-19

* ``messages`` — user/assistant chat history with client-message idempotency and an
  append-once assistant contract (``is_complete`` finalised at stream termination).
* ``refresh_sessions`` — hashed, rotated refresh tokens with CSRF binding.
* ``eval_runs`` — evaluation run storage (skeleton; execution is a later stage).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261019_0004"
down_revision: str | None = "20261019_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "message_role": ("user", "assistant", "system_event"),
    "eval_run_status": ("queued", "running", "succeeded", "failed"),
}


def _enum(name: str) -> postgresql.ENUM:
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
        "messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", _enum("message_role"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.LargeBinary, nullable=True),
        sa.Column("client_message_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("route", sa.String(40), nullable=True),
        sa.Column("finish_reason", sa.String(40), nullable=True),
        sa.Column(
            "citations_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "risk_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_complete", sa.Boolean, nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id", "conversation_id", "user_id"],
            ["conversations.shop_id", "conversations.id", "conversations.user_id"],
            name="fk_messages_conversation_same_user",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "uq_messages_client",
        "messages",
        ["shop_id", "conversation_id", "client_message_id"],
        unique=True,
        postgresql_where=sa.text("client_message_id IS NOT NULL"),
    )
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["shop_id", "conversation_id", "created_at"],
    )

    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.LargeBinary, nullable=False),
        sa.Column("csrf_token_hash", sa.LargeBinary, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(as_uuid=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id", "user_id"],
            ["users.shop_id", "users.id"],
            name="fk_refresh_sessions_user_same_shop",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("token_hash", name="uq_refresh_sessions_token_hash"),
    )
    op.create_index(
        "ix_refresh_sessions_user", "refresh_sessions", ["shop_id", "user_id", "created_at"]
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("dataset_name", sa.String(120), nullable=False),
        sa.Column("dataset_version", sa.String(40), nullable=False),
        sa.Column(
            "config_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("metrics_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", _enum("eval_run_status"), nullable=False, server_default="queued"),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name="fk_eval_runs_shop", ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_eval_runs_shop_time", "eval_runs", ["shop_id", "created_at"])


def downgrade() -> None:
    op.drop_table("eval_runs")
    op.drop_table("refresh_sessions")
    op.drop_table("messages")

    bind = op.get_bind()
    for name in reversed(list(ENUMS)):
        postgresql.ENUM(*ENUMS[name], name=name).drop(bind, checkfirst=True)
