"""Stage 18: per-conversation knowledge-base selection.

Revision ID: 20261023_0008
Revises: 20261022_0007
Create Date: 2026-10-23

The course brief requires the chat page to let a user pick one or more knowledge bases.
The selection is **conversation-scoped** (not per message): switching it affects the next
turns, while already-persisted messages keep the citations they were answered with.

Stored as a JSONB array of knowledge-base UUID strings. An **empty array means "no
restriction"** (every knowledge base visible to the shop), which is exactly the behaviour
before this migration, so no backfill is needed and existing conversations keep working.

Additive and backward compatible: existing rows default to an empty array.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261023_0008"
down_revision: str | None = "20261022_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "knowledge_base_ids_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "knowledge_base_ids_jsonb")
