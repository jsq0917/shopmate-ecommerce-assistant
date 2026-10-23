"""Per-conversation generation parameters (stage 19).

The course brief requires the chat page to configure temperature, ``top_p``, the maximum
output length and how many history turns are assembled. The overrides are stored on the
**conversation** (``conversations.generation_params_jsonb``), never on the request body, so
they survive a refresh and travel with the conversation; ``POST /chat/stream`` reads them
server-side exactly like the stage-18 knowledge-base selection.

Semantics (mirroring ``knowledge_base_ids``):

* a missing key / ``null`` means "not overridden" — the ``LLM_*`` environment default (or,
  for ``top_p``, the provider default) applies, so existing conversations keep working with
  no backfill;
* ``history_turns`` is resolved to a concrete integer (default :data:`DEFAULT_HISTORY_TURNS`)
  because the context assembly needs a ``LIMIT``, not a maybe.

Safety: the *write* path (API schema + endpoint) rejects out-of-range values and anything
above ``llm_max_tokens_cap``; :meth:`GenerationParams.resolve` additionally clamps on read,
so a row written before the cap was lowered can never stall a turn.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from shopmate_ecommerce_assistant.core.config import Settings

logger = logging.getLogger(__name__)

#: History turns used when the conversation stores no override. This is the fixed limit
#: ``ChatService.recent_history`` used before stage 19, so the default changes nothing.
DEFAULT_HISTORY_TURNS = 10

#: Upper bound for a per-conversation ``history_turns`` (course brief: 0-10).
MAX_HISTORY_TURNS = 10

#: Schema-level ceiling for ``max_tokens``; the operator-controlled
#: ``llm_max_tokens_cap`` may only lower it further.
MAX_TOKENS_CEILING = 8192


@dataclass(frozen=True, slots=True)
class GenerationParams:
    """Resolved generation parameters for one turn.

    ``temperature`` / ``top_p`` / ``max_tokens`` are ``None`` when the conversation does
    not override them; the answer model then falls back to its environment defaults
    (``top_p`` is simply not sent). ``history_turns`` is always concrete.
    """

    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    history_turns: int = DEFAULT_HISTORY_TURNS

    @classmethod
    def resolve(
        cls, stored: Mapping[str, Any] | None, *, settings: Settings
    ) -> GenerationParams:
        """Return the effective parameters for a conversation's stored overrides.

        ``stored`` comes straight from JSONB, so every value is treated as untrusted:
        non-numeric or out-of-range entries are ignored/clamped rather than trusted. A
        clamp is logged because it means a row outlived a configuration change.
        """
        data = stored if isinstance(stored, Mapping) else {}
        cap = settings.llm_max_tokens_cap
        max_tokens = _clamped_int(
            data.get("max_tokens"), low=1, high=min(cap, MAX_TOKENS_CEILING), name="max_tokens"
        )
        return cls(
            temperature=_clamped_float(
                data.get("temperature"), low=0.0, high=1.0, name="temperature"
            ),
            top_p=_clamped_float(data.get("top_p"), low=0.0, high=1.0, name="top_p"),
            max_tokens=max_tokens,
            history_turns=_clamped_int(
                data.get("history_turns"),
                low=0,
                high=MAX_HISTORY_TURNS,
                name="history_turns",
                default=DEFAULT_HISTORY_TURNS,
            ),
        )


def _as_number(value: Any) -> float | int | None:
    """Return ``value`` as a finite number, or ``None`` when it is not one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return value if isinstance(value, int) else number


def _clamped_float(
    value: Any, *, low: float, high: float, name: str
) -> float | None:
    number = _as_number(value)
    if number is None:
        return None
    if not (low <= number <= high):
        logger.warning("ignoring out-of-range generation override %s=%r", name, value)
        return None
    return float(number)


def _clamped_int(
    value: Any, *, low: int, high: int, name: str, default: int | None = None
) -> int | None:
    number = _as_number(value)
    if number is None:
        return default
    # A fractional token/turn count is not a meaningful value: refuse it instead of
    # silently truncating (the write path stores ints only, so this is a bad-row guard).
    if isinstance(number, float) and not number.is_integer():
        logger.warning("ignoring non-integer generation override %s=%r", name, value)
        return default
    if not (low <= number <= high):
        clamped = min(max(int(number), low), high)
        logger.warning(
            "clamping generation override %s=%r to %d (cap %d)", name, value, clamped, high
        )
        return clamped
    return int(number)


__all__ = [
    "DEFAULT_HISTORY_TURNS",
    "MAX_HISTORY_TURNS",
    "MAX_TOKENS_CEILING",
    "GenerationParams",
]
