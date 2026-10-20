"""Authentication primitives: JWT, captcha, password hashing and permissions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt as pyjwt
import pytest

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.security import (
    ACCESS_TOKEN_ISSUER,
    AccessContext,
    AuthError,
    decode_access_token,
    hash_password,
    issue_access_token,
    issue_captcha,
    permissions_for,
    verify_captcha,
    verify_password,
)
from shopmate_ecommerce_assistant.db.models.enums import UserRole


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret="unit-test-secret",
        access_token_ttl_seconds=900,
        captcha_ttl_seconds=300,
    )


def _context(**overrides) -> AccessContext:
    base = dict(
        shop_id=uuid4(),
        user_id=uuid4(),
        role=UserRole.SHOPPER,
        permissions=frozenset(),
    )
    base.update(overrides)
    return AccessContext(**base)


def test_access_token_round_trip(settings: Settings) -> None:
    context = _context()
    token = issue_access_token(settings, context)
    decoded = decode_access_token(settings, token)

    assert decoded.shop_id == context.shop_id
    assert decoded.user_id == context.user_id
    assert decoded.role is UserRole.SHOPPER
    assert decoded.permissions == frozenset()


def test_access_token_carries_permissions(settings: Settings) -> None:
    context = _context(role=UserRole.SUPPORT, permissions=permissions_for(UserRole.SUPPORT))
    decoded = decode_access_token(settings, issue_access_token(settings, context))

    assert decoded.role is UserRole.SUPPORT
    assert "support:ticket:read" in decoded.permissions
    assert decoded.has_permission("support:ticket:read")


def test_expired_token_raises_auth_error(settings: Settings) -> None:
    short = settings.model_copy(update={"access_token_ttl_seconds": -1})
    token = issue_access_token(short, _context())

    with pytest.raises(AuthError) as exc:
        decode_access_token(settings, token)
    assert exc.value.code == "UNAUTHENTICATED"


def test_tampered_token_raises_auth_error(settings: Settings) -> None:
    token = issue_access_token(settings, _context())
    header, payload, signature = token.split(".")
    forged_payload = payload[:-2] + ("AA" if payload[-2:] != "AA" else "BB")

    with pytest.raises(AuthError):
        decode_access_token(settings, f"{header}.{forged_payload}.{signature}")


def test_token_with_wrong_secret_raises(settings: Settings) -> None:
    token = issue_access_token(settings, _context())
    other = settings.model_copy(update={"jwt_secret": "a-different-secret"})

    with pytest.raises(AuthError):
        decode_access_token(other, token)


def test_token_with_wrong_issuer_raises(settings: Settings) -> None:
    context = _context()
    now = datetime.now(UTC)
    payload = {
        "sub": str(context.user_id),
        "shop_id": str(context.shop_id),
        "role": context.role.value,
        "permissions": [],
        "iat": now,
        "exp": now + timedelta(seconds=900),
        "iss": "someone-else",
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    with pytest.raises(AuthError):
        decode_access_token(settings, token)


def test_captcha_accepts_correct_answer_and_rejects_wrong(settings: Settings) -> None:
    challenge = issue_captcha(settings)

    assert verify_captcha(settings, challenge.token, challenge._answer) is True
    assert verify_captcha(settings, challenge.token, "999999") is False
    assert verify_captcha(settings, "not-a-token", challenge._answer) is False


def test_password_hash_round_trip_and_rejection() -> None:
    hashed = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_role_permissions_mapping() -> None:
    assert permissions_for(UserRole.SHOPPER) == frozenset()
    assert "support:conversation:read" in permissions_for(UserRole.SUPPORT)
    assert "admin:knowledge:read" in permissions_for(UserRole.ADMIN)
    # Admin must not implicitly gain support conversation read (docs/06-api.md §12).
    assert "support:conversation:read" not in permissions_for(UserRole.ADMIN)


def test_access_token_issuer_constant() -> None:
    assert ACCESS_TOKEN_ISSUER == "shopmate-api"
