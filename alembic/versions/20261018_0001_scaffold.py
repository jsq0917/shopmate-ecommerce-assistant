"""Initialize the migration chain.

Revision ID: 20261018_0001
Revises:
Create Date: 2026-10-18
"""

from collections.abc import Sequence

revision: str = "20261018_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the baseline revision without business tables."""


def downgrade() -> None:
    """Remove the baseline revision without business tables."""
