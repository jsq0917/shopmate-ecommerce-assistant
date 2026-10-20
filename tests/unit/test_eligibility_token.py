"""Unit tests for eligibility token signing and binding verification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from shopmate_ecommerce_assistant.domain.returns.tokens import (
    EligibilityClaims,
    EligibilityTokenError,
    issue_eligibility_token,
    read_eligibility_token,
    verify_eligibility_token,
)

SECRET = "test-secret-key-1234567890"


def _claims(**overrides) -> EligibilityClaims:
    now = datetime.now(UTC)
    base = dict(
        shop_id=uuid4(),
        user_id=uuid4(),
        order_id=uuid4(),
        order_item_id=uuid4(),
        reason_code="SIZE_OR_FIT",
        rule_version="demo-return-v1",
        decision="eligible",
        issued_at=now,
        expires_at=now + timedelta(minutes=10),
        conversation_id=uuid4(),
    )
    base.update(overrides)
    return EligibilityClaims(**base)


def test_roundtrip_round_trip() -> None:
    claims = _claims()
    token = issue_eligibility_token(claims, secret=SECRET)
    parsed = read_eligibility_token(token, secret=SECRET)
    assert parsed == claims


def test_verify_accepts_matching_binding() -> None:
    claims = _claims()
    token = issue_eligibility_token(claims, secret=SECRET)
    verified = verify_eligibility_token(
        token,
        secret=SECRET,
        shop_id=claims.shop_id,
        user_id=claims.user_id,
        order_id=claims.order_id,
        order_item_id=claims.order_item_id,
        reason_code=claims.reason_code,
        now=claims.issued_at + timedelta(seconds=1),
    )
    assert verified.order_id == claims.order_id


def test_tampered_payload_is_rejected() -> None:
    token = issue_eligibility_token(_claims(), secret=SECRET)
    version, body, signature = token.split(".")
    forged = f"{version}.{body[:-2]}AA.{signature}"
    with pytest.raises(EligibilityTokenError):
        read_eligibility_token(forged, secret=SECRET)


def test_wrong_secret_is_rejected() -> None:
    token = issue_eligibility_token(_claims(), secret=SECRET)
    with pytest.raises(EligibilityTokenError):
        read_eligibility_token(token, secret="another-secret-key-9999")


def test_binding_mismatch_is_rejected() -> None:
    claims = _claims()
    token = issue_eligibility_token(claims, secret=SECRET)
    other = uuid4()
    with pytest.raises(EligibilityTokenError):
        verify_eligibility_token(
            token,
            secret=SECRET,
            shop_id=claims.shop_id,
            user_id=claims.user_id,
            order_id=other,
            order_item_id=claims.order_item_id,
            reason_code=claims.reason_code,
            now=claims.issued_at,
        )


def test_expired_token_is_rejected() -> None:
    claims = _claims(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    token = issue_eligibility_token(claims, secret=SECRET)
    with pytest.raises(EligibilityTokenError):
        verify_eligibility_token(
            token,
            secret=SECRET,
            shop_id=claims.shop_id,
            user_id=claims.user_id,
            order_id=claims.order_id,
            order_item_id=claims.order_item_id,
            reason_code=claims.reason_code,
            now=datetime.now(UTC),
        )


def test_non_eligible_decision_is_rejected() -> None:
    claims = _claims(decision="needs_manual_review")
    token = issue_eligibility_token(claims, secret=SECRET)
    with pytest.raises(EligibilityTokenError):
        verify_eligibility_token(
            token,
            secret=SECRET,
            shop_id=claims.shop_id,
            user_id=claims.user_id,
            order_id=claims.order_id,
            order_item_id=claims.order_item_id,
            reason_code=claims.reason_code,
            now=claims.issued_at,
        )


def test_garbage_token_is_rejected() -> None:
    with pytest.raises(EligibilityTokenError):
        read_eligibility_token("not-a-token", secret=SECRET)


def test_weak_secret_is_rejected() -> None:
    with pytest.raises(EligibilityTokenError):
        issue_eligibility_token(_claims(), secret="short")
