"""Deterministic identifiers for synthetic data and knowledge artefacts.

Every seeded row derives its primary key from natural keys, which makes re-running the
seeders idempotent without relying on database-generated UUIDs.
"""

from uuid import UUID, uuid5

NAMESPACE = UUID("6f1d6a2e-7c4b-5a90-9d3e-2b8f4c1a5e70")


def stable_uuid(*parts: str) -> UUID:
    """Return a deterministic UUID for the given natural-key parts."""
    return uuid5(NAMESPACE, "|".join(parts))
