"""Repository layer: PostgreSQL access for the structured commerce and knowledge paths."""

from shopmate_ecommerce_assistant.db.repositories.knowledge import (
    ChunkMetadata,
    authorization_issues,
    load_chunk_metadata,
)

__all__ = ["ChunkMetadata", "authorization_issues", "load_chunk_metadata"]
