"""Authentication and token security primitives (stage 10).

This module owns what must never be improvised:

* Argon2 password hashing (no plaintext, no fast hash);
* short-lived access JWTs carrying identity, tenant and role — identity always comes
  from the verified token, never from a request body;
* opaque, rotated refresh tokens stored only as SHA-256 digests;
* a stateless arithmetic captcha: the answer hash is signed inside a short-lived
  ``captcha_token``, so the server never needs to store plaintext answers;
* a synchronizer-token CSRF pair bound to each refresh session.

All secrets read from :class:`Settings`; the committed defaults are placeholders for local
development exactly like the database password.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt as pyjwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.db.models.enums import UserRole

_password_hasher = PasswordHasher()

ACCESS_TOKEN_ISSUER = "shopmate-api"

#: Default role permissions (contract §12.1 / §13). Admin intentionally does NOT get
#: ``support:conversation:read`` — that must be granted explicitly (docs/06-api.md §12).
PERMISSIONS_BY_ROLE: dict[UserRole, tuple[str, ...]] = {
    UserRole.SHOPPER: (),
    UserRole.SUPPORT: (
        "support:ticket:read",
        "support:ticket:write",
        "support:conversation:read",
        "support:quality_label:write",
    ),
    UserRole.ADMIN: (
        "admin:knowledge:read",
        "admin:knowledge:write",
        "admin:eval:read",
        "admin:eval:write",
        "admin:model:read",
    ),
}


class AuthError(Exception):
    """An authentication/authorization failure with a safe, non-leaking message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class AccessContext:
    """Verified identity + tenant scope for one request.

    ``permissions`` is derived from the role at token issue time; a caller can never widen
    it via a request payload.
    """

    shop_id: UUID
    user_id: UUID
    role: UserRole
    permissions: frozenset[str] = field(default_factory=frozenset)

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


def hash_password(password: str) -> str:
    """Return an Argon2id hash of ``password``."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return True when ``password`` matches ``password_hash`` (constant-time)."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def issue_access_token(settings: Settings, context: AccessContext) -> str:
    """Return a signed access JWT for ``context``."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(context.user_id),
        "shop_id": str(context.shop_id),
        "role": context.role.value,
        "permissions": sorted(context.permissions),
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_ttl_seconds),
        "iss": ACCESS_TOKEN_ISSUER,
        "jti": secrets.token_hex(8),
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(settings: Settings, token: str) -> AccessContext:
    """Verify an access JWT and return its identity context.

    Raises:
        AuthError: on an expired, malformed or otherwise invalid token.
    """
    try:
        payload = pyjwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=ACCESS_TOKEN_ISSUER,
        )
    except pyjwt.ExpiredSignatureError as exc:
        raise AuthError("UNAUTHENTICATED", "登录已过期，请重新登录。") from exc
    except pyjwt.InvalidTokenError as exc:
        raise AuthError("UNAUTHENTICATED", "登录状态无效，请重新登录。") from exc

    try:
        user_id = UUID(str(payload["sub"]))
        shop_id = UUID(str(payload["shop_id"]))
        role = UserRole(str(payload["role"]))
        permissions = frozenset(str(item) for item in (payload.get("permissions") or []))
    except (KeyError, ValueError, TypeError) as exc:
        raise AuthError("UNAUTHENTICATED", "登录状态无效，请重新登录。") from exc
    return AccessContext(shop_id=shop_id, user_id=user_id, role=role, permissions=permissions)


def new_refresh_token() -> str:
    """Return an opaque, high-entropy refresh token (never stored in clear)."""
    return secrets.token_urlsafe(48)


def new_csrf_token() -> str:
    """Return an opaque CSRF synchronizer token."""
    return secrets.token_urlsafe(32)


def sha256_digest(value: str) -> bytes:
    """Return the SHA-256 digest used to store tokens and CSRF tokens."""
    return hashlib.sha256(value.encode("utf-8")).digest()


class CaptchaChallenge:
    """A stateless captcha: a signed ``token`` plus a human-answerable ``question``."""

    def __init__(self, token: str, question: str, answer: str) -> None:
        self.token = token
        self.question = question
        # The answer is never persisted or logged; only its hash enters the signed token.
        self._answer = answer


def issue_captcha(settings: Settings) -> CaptchaChallenge:
    """Return a signed captcha challenge with a random arithmetic answer."""
    left = secrets.randbelow(9) + 1
    right = secrets.randbelow(9) + 1
    answer = str(left + right)
    now = datetime.now(UTC)
    payload = {
        "answer_hash": sha256_digest(answer).hex(),
        "iat": now,
        "exp": now + timedelta(seconds=settings.captcha_ttl_seconds),
        "iss": ACCESS_TOKEN_ISSUER,
        "nonce": secrets.token_hex(8),
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return CaptchaChallenge(token=token, question=f"{left} + {right} = ?", answer=answer)


def verify_captcha(settings: Settings, captcha_token: str, answer: str) -> bool:
    """Return True when ``answer`` matches the signed captcha challenge (unexpired)."""
    try:
        payload = pyjwt.decode(
            captcha_token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=ACCESS_TOKEN_ISSUER,
        )
    except pyjwt.InvalidTokenError:
        return False
    expected = str(payload.get("answer_hash", ""))
    return expected and secrets.compare_digest(expected, sha256_digest(answer.strip()).hex())


def permissions_for(role: UserRole) -> frozenset[str]:
    """Return the default permission set for a role."""
    return frozenset(PERMISSIONS_BY_ROLE.get(role, ()))


__all__ = [
    "ACCESS_TOKEN_ISSUER",
    "PERMISSIONS_BY_ROLE",
    "AccessContext",
    "AuthError",
    "CaptchaChallenge",
    "decode_access_token",
    "hash_password",
    "issue_access_token",
    "issue_captcha",
    "new_csrf_token",
    "new_refresh_token",
    "permissions_for",
    "sha256_digest",
    "verify_captcha",
    "verify_password",
]
