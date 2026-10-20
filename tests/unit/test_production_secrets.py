"""Production must not boot with the repository's development secrets (stage 14 hardening).

``Settings`` ships ``shopmate-dev-*`` placeholders so a fresh clone runs locally. Those values
are public, so a production process that keeps them would accept forged access tokens and
forged return-eligibility tokens. ``create_app`` therefore refuses to build the app.
"""

import pytest

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.main import create_app


def test_production_rejects_development_jwt_secret() -> None:
    settings = Settings(_env_file=None, app_env="production")

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        create_app(settings=settings)


def test_production_rejects_development_tool_token_secret() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="a" * 40,
    )

    with pytest.raises(RuntimeError, match="TOOL_TOKEN_SECRET"):
        create_app(settings=settings)


def test_production_accepts_injected_secrets() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret="b" * 40,
        tool_token_secret="c" * 40,
        trusted_hosts="127.0.0.1,localhost,shopmate.example.invalid",
    )

    app = create_app(settings=settings)

    assert app.title == settings.app_name


def test_local_environments_keep_development_secrets() -> None:
    """Demo/development/test flows must stay usable without extra configuration."""
    for app_env in ("demo", "development", "test"):
        settings = Settings(_env_file=None, app_env=app_env)
        settings.ensure_production_secrets()  # must not raise
