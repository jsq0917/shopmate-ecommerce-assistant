"""LLM profile resolution (2026-10-23).

The answer model is DeepSeek by default; ``LLM_PROFILE`` exists so the whole stack can be
switched to another OpenAI-compatible endpoint with one variable (``qwen`` aligns with the
course brief, ``local`` is an offline smoke test only). These tests pin two invariants:

* the default is DeepSeek (production / development / evaluation baseline);
* **explicit** ``LLM_BASE_URL`` / ``LLM_MODEL`` always beat the preset.
"""

from __future__ import annotations

import httpx
import pytest

# Import `safety` first: `rag.policy_qa` imports `rag.retrieval` at module load, which pulls
# the repository/models layer back through `safety.output_guard`. Importing `policy_qa`
# first hits that known cycle (documented in docs/project-status.md §23.5); the full suite
# hides it because an earlier test module already loaded the other side.
from shopmate_ecommerce_assistant import safety as _safety  # noqa: F401
from shopmate_ecommerce_assistant.core.config import LLM_PROFILES, Settings

_LLM_ENV = (
    "LLM_PROFILE",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_TIMEOUT_SECONDS",
    "LLM_TEMPERATURE",
    "LLM_MAX_TOKENS",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop any LLM_* value from the process env and skip the .env file."""
    for name in _LLM_ENV:
        monkeypatch.delenv(name, raising=False)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_default_profile_is_deepseek() -> None:
    settings = _settings()
    assert settings.llm_profile == "deepseek"
    assert settings.llm_base_url == "https://api.deepseek.com"
    assert settings.llm_model == "deepseek-flash"
    assert settings.llm_temperature == pytest.approx(0.1)
    assert settings.llm_timeout_seconds == pytest.approx(60.0)
    assert settings.llm_max_tokens == 0


def test_explicit_values_beat_the_profile() -> None:
    settings = _settings(
        llm_profile="qwen",
        llm_base_url="https://example.invalid/v1",
        llm_model="my-own-model",
    )
    assert settings.llm_base_url == "https://example.invalid/v1"
    assert settings.llm_model == "my-own-model"


def test_qwen_profile_fills_dashscope_endpoint() -> None:
    settings = _settings(llm_profile="qwen")
    assert settings.llm_base_url == LLM_PROFILES["qwen"]["base_url"]
    assert settings.llm_model == "qwen-max"


def test_local_profile_is_offline_smoke_test_only() -> None:
    """``local`` must stay reachable but is documented as not-an-evaluation-baseline."""
    settings = _settings(llm_profile="local")
    assert settings.llm_base_url == "http://127.0.0.1:11434/v1"
    assert settings.llm_model == "qwen2.5:7b"


def test_answer_model_payload_carries_max_tokens_only_when_set() -> None:
    from shopmate_ecommerce_assistant.rag.policy_qa import OpenAICompatibleAnswerModel

    model = OpenAICompatibleAnswerModel(_settings(llm_base_url="http://x/v1", llm_model="m"))
    assert model._max_tokens == 0

    limited = OpenAICompatibleAnswerModel(
        _settings(llm_base_url="http://x/v1", llm_model="m", llm_max_tokens=256)
    )
    assert limited._max_tokens == 256


# -- stage 19: per-conversation generation overrides reach the payload ---------


def _captured_payload(**generation: object) -> dict:
    """Call the model once with a patched transport and return the JSON body it sent."""
    from unittest.mock import patch

    from shopmate_ecommerce_assistant.core.generation import GenerationParams
    from shopmate_ecommerce_assistant.rag.policy_qa import OpenAICompatibleAnswerModel

    model = OpenAICompatibleAnswerModel(
        _settings(
            llm_base_url="http://x/v1",
            llm_model="m",
            llm_temperature=0.1,
            llm_max_tokens=0,
        )
    )
    sent: dict = {}

    def _fake_post(self, url, *, json=None, headers=None):  # noqa: ANN001 - httpx shape
        sent.update(json or {})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "好的"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
            request=httpx.Request("POST", str(url)),
        )

    with patch("httpx.Client.post", _fake_post):
        model.complete(
            system="s",
            user="u",
            generation=GenerationParams(**generation) if generation else None,  # type: ignore[arg-type]
        )
    return sent


def test_generation_overrides_reach_the_payload() -> None:
    payload = _captured_payload(temperature=0.8, top_p=0.9, max_tokens=512)
    assert payload["temperature"] == 0.8
    assert payload["top_p"] == 0.9
    assert payload["max_tokens"] == 512


def test_no_generation_keeps_the_environment_payload() -> None:
    """``generation=None`` must reproduce the pre-stage-19 body exactly: temperature from
    the environment, no ``top_p`` key, no ``max_tokens`` when the env does not set one."""
    payload = _captured_payload()
    assert payload["temperature"] == 0.1
    assert "top_p" not in payload
    assert "max_tokens" not in payload


def test_partial_overrides_only_replace_what_they_set() -> None:
    payload = _captured_payload(max_tokens=256)
    assert payload["temperature"] == 0.1  # untouched environment default
    assert "top_p" not in payload  # still not sent
    assert payload["max_tokens"] == 256


def test_history_turns_never_reaches_the_payload() -> None:
    """``history_turns`` shapes the context assembly upstream; the model never sees it."""
    payload = _captured_payload(history_turns=0)
    assert "history_turns" not in payload
    assert payload["temperature"] == 0.1
