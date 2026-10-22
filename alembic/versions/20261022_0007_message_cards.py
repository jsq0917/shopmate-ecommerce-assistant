"""Stage 17: persist product cards on assistant messages.

Revision ID: 20261022_0007
Revises: 20261022_0006
Create Date: 2026-10-22

The chat stream emits ``product_card`` events once; without a stored copy, reopening a
conversation shows text that says "点开卡片" with no cards. This column keeps the exact card
payloads (prices/stock as of that turn) alongside the message.

Additive and backward compatible: existing rows default to an empty array.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261022_0007"
down_revision: str | None = "20261022_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "cards_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("messages", "cards_jsonb")
