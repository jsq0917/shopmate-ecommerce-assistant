"""Stage 19: per-conversation generation parameters.

Covers the two halves of the safety contract:

* **resolution** (:meth:`GenerationParams.resolve`) — a missing/``null`` override falls back
  to the environment default, a stale ``max_tokens`` is clamped to the operator cap, and a
  hand-edited JSONB row can never smuggle an out-of-range value into the LLM call;
* **schema** — an out-of-range request is rejected at the door, so a bad value is never
  stored in the first place.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

# Import `safety` first: `rag.policy_qa` imports `rag.retrieval` at module load, which pulls
# the repository/models layer back through `safety.output_guard`. Same cycle note as
# tests/unit/test_llm_profile.py.
from shopmate_ecommerce_assistant import safety as _safety  # noqa: F401
from shopmate_ecommerce_assistant.api.schemas import (
    ConversationGenerationParams,
    UpdateGenerationParamsRequest,
)
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.generation import (
    DEFAULT_HISTORY_TURNS,
    MAX_HISTORY_TURNS,
    GenerationParams,
)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


# -- resolve ---------------------------------------------------------------


def test_no_overrides_falls_back_to_the_environment() -> None:
    resolved = GenerationParams.resolve(None, settings=_settings(llm_temperature=0.2))
    assert resolved == GenerationParams(
        temperature=None, top_p=None, max_tokens=None, history_turns=DEFAULT_HISTORY_TURNS
    )


def test_stored_overrides_are_kept_verbatim() -> None:
    resolved = GenerationParams.resolve(
        {"temperature": 0.7, "top_p": 0.9, "max_tokens": 512, "history_turns": 3},
        settings=_settings(),
    )
    assert resolved == GenerationParams(temperature=0.7, top_p=0.9, max_tokens=512, history_turns=3)


def test_history_turns_zero_is_a_meaningful_value() -> None:
    """0 disables history entirely; it must not be confused with "unset"."""
    resolved = GenerationParams.resolve({"history_turns": 0}, settings=_settings())
    assert resolved.history_turns == 0


def test_max_tokens_above_the_cap_is_clamped_not_trusted() -> None:
    """A row written before the cap was lowered must not stall a turn."""
    resolved = GenerationParams.resolve(
        {"max_tokens": 99999}, settings=_settings(llm_max_tokens_cap=2048)
    )
    assert resolved.max_tokens == 2048


def test_max_tokens_at_the_cap_is_kept() -> None:
    resolved = GenerationParams.resolve(
        {"max_tokens": 2048}, settings=_settings(llm_max_tokens_cap=2048)
    )
    assert resolved.max_tokens == 2048


def test_out_of_range_float_override_is_ignored() -> None:
    resolved = GenerationParams.resolve({"temperature": 1.5, "top_p": -0.1}, settings=_settings())
    assert resolved.temperature is None
    assert resolved.top_p is None


def test_history_turns_above_the_limit_is_clamped() -> None:
    resolved = GenerationParams.resolve({"history_turns": 99}, settings=_settings())
    assert resolved.history_turns == MAX_HISTORY_TURNS


@pytest.mark.parametrize(
    "stored",
    [
        "not-a-mapping",
        {"temperature": "0.5"},
        {"temperature": True},  # bool is not a usable number here
        {"max_tokens": 1.5},  # clamped into range, but a float stays a float
        {"history_turns": None},
        [("temperature", 0.5)],
    ],
)
def test_untrusted_rows_degrade_to_defaults(stored: object) -> None:
    resolved = GenerationParams.resolve(stored, settings=_settings())  # type: ignore[arg-type]
    assert resolved == GenerationParams()


def test_float_max_tokens_override_is_coerced_to_int() -> None:
    resolved = GenerationParams.resolve({"max_tokens": 512.0}, settings=_settings())
    assert resolved.max_tokens == 512
    assert isinstance(resolved.max_tokens, int)


# -- schema ----------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"temperature": 1.5},
        {"temperature": -0.01},
        {"top_p": 2.0},
        {"top_p": -1},
        {"max_tokens": 0},
        {"max_tokens": -1},
        {"max_tokens": 10_000_000},
        {"history_turns": -1},
        {"history_turns": MAX_HISTORY_TURNS + 1},
    ],
)
def test_out_of_range_request_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        UpdateGenerationParamsRequest(**payload)


def test_empty_request_is_valid_and_clears_nothing() -> None:
    body = UpdateGenerationParamsRequest()
    assert body.model_dump(exclude_unset=True) == {}


def test_explicit_null_is_a_set_field_that_clears_the_override() -> None:
    body = UpdateGenerationParamsRequest(temperature=None, history_turns=4)
    assert body.model_dump(exclude_unset=True) == {"temperature": None, "history_turns": 4}


def test_response_model_renders_unset_overrides_as_null() -> None:
    item = ConversationGenerationParams.model_validate({"temperature": 0.5})
    dumped = item.model_dump()
    assert dumped == {"temperature": 0.5, "top_p": None, "max_tokens": None, "history_turns": None}


def test_response_model_rejects_a_corrupt_stored_row() -> None:
    with pytest.raises(ValidationError):
        ConversationGenerationParams.model_validate({"temperature": 5.0})
