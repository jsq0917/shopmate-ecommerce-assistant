"""Stage 16: support workbench state fields + answer quality labels.

Revision ID: 20261020_0005
Revises: 20261019_0004
Create Date: 2026-10-20

Additive only — no column type change, no data rewrite, no history back-fill:

* ``handoff_tickets.resolution_summary`` / ``handoff_tickets.close_reason`` — the two
  fields ``docs/06-api.md`` §12 requires for ``PATCH /api/v1/support/tickets/{id}``.
  Both nullable, so existing ``open`` tickets stay valid.
* ``support_quality_labels`` — audit trail for the support agent's
  ``correct/incorrect/needs_knowledge`` verdict on an assistant answer. Labels never
  mutate the knowledge version, retrieval results or model parameters.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261020_0005"
down_revision: str | None = "20261019_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
    op.add_column("handoff_tickets", sa.Column("resolution_summary", sa.Text(), nullable=True))
    op.add_column(
        "handoff_tickets", sa.Column("close_reason", sa.String(length=240), nullable=True)
    )

    op.create_table(
        "support_quality_labels",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("ticket_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("message_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=20), nullable=False),
        sa.Column("reason_summary", sa.String(length=240), nullable=True),
        sa.Column("labeled_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "is_synthetic", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "label IN ('correct', 'incorrect', 'needs_knowledge')",
            name="ck_quality_labels_label",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name="fk_quality_labels_shop", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["handoff_tickets.id"],
            name="fk_quality_labels_ticket",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_quality_labels_message", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "shop_id", "message_id", "labeled_by", name="uq_quality_labels_message_labeler"
        ),
        sa.Index("ix_quality_labels_ticket", "shop_id", "ticket_id", "created_at"),
        sa.Index("ix_quality_labels_label", "shop_id", "label", "created_at"),
    )


def downgrade() -> None:
    op.drop_index("ix_quality_labels_label", table_name="support_quality_labels")
    op.drop_index("ix_quality_labels_ticket", table_name="support_quality_labels")
    op.drop_table("support_quality_labels")
    op.drop_column("handoff_tickets", "close_reason")
    op.drop_column("handoff_tickets", "resolution_summary")
