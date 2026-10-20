"""Signed eligibility tokens.

``check_return_eligibility`` returns an opaque token; ``create_return_request`` accepts one
only when the signature, the expiry, the decision and the binding (shop + user + order +
order item + reason + rule version) all match. The model cannot mint or edit a token
because the signing key never leaves the server, and it cannot swap an eligible token onto
a different order item because the binding is part of the signed payload.

Format: ``v1.<base64url(payload)>.<base64url(hmac_sha256("v1.<payload>"))>``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

TOKEN_VERSION = "v1"
MIN_SECRET_LENGTH = 16


class EligibilityTokenError(Exception):
    """Raised for any unusable token. ``reason`` is for logs, never for the model."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class EligibilityClaims:
    """What an eligibility token asserts, bound to one order item and one reason."""

    shop_id: UUID
    user_id: UUID
    order_id: UUID
    order_item_id: UUID
    reason_code: str
    rule_version: str
    decision: str
    issued_at: datetime
    expires_at: datetime
    conversation_id: UUID | None = None


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(signing_input: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()


def _require_secret(secret: str) -> None:
    if len(secret) < MIN_SECRET_LENGTH:
        raise EligibilityTokenError("weak_secret")


def _serialize(claims: EligibilityClaims) -> dict[str, object]:
    return {
        "shop_id": str(claims.shop_id),
        "user_id": str(claims.user_id),
        "order_id": str(claims.order_id),
        "order_item_id": str(claims.order_item_id),
        "reason_code": claims.reason_code,
        "rule_version": claims.rule_version,
        "decision": claims.decision,
        "issued_at": claims.issued_at.astimezone(UTC).isoformat(),
        "expires_at": claims.expires_at.astimezone(UTC).isoformat(),
        "conversation_id": None if claims.conversation_id is None else str(claims.conversation_id),
    }


def issue_eligibility_token(claims: EligibilityClaims, *, secret: str) -> str:
    """Return an opaque, signed token for an eligible decision."""
    _require_secret(secret)
    body = _b64encode(
        json.dumps(_serialize(claims), sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{TOKEN_VERSION}.{body}".encode("ascii")
    return f"{TOKEN_VERSION}.{body}.{_b64encode(_sign(signing_input, secret))}"


def read_eligibility_token(token: str, *, secret: str) -> EligibilityClaims:
    """Verify the signature/shape and return the claims (expiry is checked separately)."""
    _require_secret(secret)
    if not isinstance(token, str) or token.count(".") != 2:
        raise EligibilityTokenError("malformed")
    version, body, signature = token.split(".")
    if version != TOKEN_VERSION:
        raise EligibilityTokenError("unsupported_version")

    try:
        expected = _sign(f"{version}.{body}".encode("ascii"), secret)
        provided = _b64decode(signature)
    except (ValueError, UnicodeEncodeError) as exc:
        raise EligibilityTokenError("malformed") from exc
    if not hmac.compare_digest(expected, provided):
        raise EligibilityTokenError("bad_signature")

    try:
        payload = json.loads(_b64decode(body))
        return EligibilityClaims(
            shop_id=UUID(payload["shop_id"]),
            user_id=UUID(payload["user_id"]),
            order_id=UUID(payload["order_id"]),
            order_item_id=UUID(payload["order_item_id"]),
            reason_code=str(payload["reason_code"]),
            rule_version=str(payload["rule_version"]),
            decision=str(payload["decision"]),
            issued_at=datetime.fromisoformat(payload["issued_at"]),
            expires_at=datetime.fromisoformat(payload["expires_at"]),
            conversation_id=(
                None if payload.get("conversation_id") is None else UUID(payload["conversation_id"])
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EligibilityTokenError("malformed") from exc


def verify_eligibility_token(
    token: str,
    *,
    secret: str,
    shop_id: UUID,
    user_id: UUID,
    order_id: UUID,
    order_item_id: UUID,
    reason_code: str,
    now: datetime,
) -> EligibilityClaims:
    """Verify signature, expiry and every binding element in one call."""
    claims = read_eligibility_token(token, secret=secret)
    if claims.decision != "eligible":
        raise EligibilityTokenError("not_eligible")
    if claims.shop_id != shop_id:
        raise EligibilityTokenError("shop_mismatch")
    if claims.user_id != user_id:
        raise EligibilityTokenError("user_mismatch")
    if claims.order_id != order_id:
        raise EligibilityTokenError("order_mismatch")
    if claims.order_item_id != order_item_id:
        raise EligibilityTokenError("item_mismatch")
    if claims.reason_code != reason_code:
        raise EligibilityTokenError("reason_mismatch")
    if claims.expires_at <= now.astimezone(UTC):
        raise EligibilityTokenError("expired")
    return claims


__all__ = [
    "EligibilityClaims",
    "EligibilityTokenError",
    "MIN_SECRET_LENGTH",
    "TOKEN_VERSION",
    "issue_eligibility_token",
    "read_eligibility_token",
    "verify_eligibility_token",
]
