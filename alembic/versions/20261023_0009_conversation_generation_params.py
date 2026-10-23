"""Stage 19: per-conversation generation parameters.

Revision ID: 20261023_0009
Revises: 20261023_0008
Create Date: 2026-10-23

The course brief requires the chat page to configure temperature, top_p, the maximum
output tokens and the number of history turns. The overrides are **conversation-scoped**
(not per message), exactly like the stage-18 knowledge-base selection: switching them
affects the next turns, while already-persisted messages keep what they were answered with.

Stored as a JSONB object. A **missing key or ``null`` means "not overridden"** — the
``LLM_*`` environment default (or, for ``top_p``, the provider default) applies, which is
exactly the behaviour before this migration, so no backfill is needed and existing
conversations keep working.

Additive and backward compatible: existing rows default to an empty object.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261023_0009"
down_revision: str | None = "20261023_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "generation_params_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "generation_params_jsonb")
