"""Chat orchestration primitives (stage 8: routing only).

The router decides *which* path a turn may take; tool execution, answer composition and
SSE streaming are wired in later stages. Keeping the package import-light avoids pulling
FastAPI into unit tests of routing rules.
"""

from shopmate_ecommerce_assistant.agents.router import (
    ALLOWED_TOOLS,
    CLARIFICATION_TEXT,
    Intent,
    IntentRoute,
    RoutePath,
    route_intent,
)

__all__ = [
    "ALLOWED_TOOLS",
    "CLARIFICATION_TEXT",
    "Intent",
    "IntentRoute",
    "RoutePath",
    "route_intent",
]
