"""Stage-17 corpus expansion — new merchandise categories.

Aggregates the three category modules into ``CATEGORY_DOCS``. Imported by
``knowledge_corpus`` after its own definitions (see the import block at the
bottom of that module) so the shared primitives can live in ``corpus_types``.
"""

from __future__ import annotations

from shopmate_ecommerce_assistant.synthetic.corpus_types import PolicyDoc
from shopmate_ecommerce_assistant.synthetic.knowledge_corpus_v2_apparel import (
    APPAREL_DOCS,
)
from shopmate_ecommerce_assistant.synthetic.knowledge_corpus_v2_digital import (
    DIGITAL_DOCS,
)
from shopmate_ecommerce_assistant.synthetic.knowledge_corpus_v2_home import (
    FURNITURE_DOCS,
)

CATEGORY_DOCS: tuple[PolicyDoc, ...] = APPAREL_DOCS + FURNITURE_DOCS + DIGITAL_DOCS

__all__ = ["CATEGORY_DOCS"]
