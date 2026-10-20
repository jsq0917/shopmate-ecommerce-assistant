"""Access-control unit tests for the injected ToolContext.

These cover the identity/role boundary directly (no database): a shopper may only act for
themselves, a support/admin context needs an authorized scope, and a write is refused for
everyone except a self-service shopper.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from shopmate_ecommerce_assistant.core.errors import ToolError
from shopmate_ecommerce_assistant.db.models.enums import UserRole
from shopmate_ecommerce_assistant.tools.context import ToolContext


def _ctx(role, *, actor=None, effective=None, permissions=()):
    return ToolContext(
        shop_id=uuid4(),
        actor_user_id=actor or uuid4(),
        role=role,
        request_id=uuid4(),
        trace_id=uuid4(),
        effective_user_id=effective,
        permissions=frozenset(permissions),
    )


def test_shopper_self_order_read_ok() -> None:
    _ctx(UserRole.SHOPPER).ensure_order_read()


def test_support_without_scope_forbidden() -> None:
    ctx = _ctx(UserRole.SUPPORT, effective=uuid4())
    with pytest.raises(ToolError) as info:
        ctx.ensure_order_read()
    assert info.value.code.value == "FORBIDDEN"


def test_support_with_scope_read_ok() -> None:
    _ctx(
        UserRole.SUPPORT, effective=uuid4(), permissions=("support:conversation:read",)
    ).ensure_order_read()


def test_admin_requires_explicit_scope() -> None:
    with pytest.raises(ToolError):
        _ctx(UserRole.ADMIN, effective=uuid4()).ensure_order_read()
    _ctx(
        UserRole.ADMIN, effective=uuid4(), permissions=("support:conversation:read",)
    ).ensure_order_read()


def test_shopper_cannot_impersonate() -> None:
    ctx = _ctx(UserRole.SHOPPER, effective=uuid4())
    with pytest.raises(ToolError) as info:
        ctx.ensure_order_read()
    assert info.value.code.value == "FORBIDDEN"


@pytest.mark.parametrize("role", [UserRole.SUPPORT, UserRole.ADMIN])
def test_only_shopper_can_submit_return(role) -> None:
    ctx = _ctx(role)
    with pytest.raises(ToolError) as info:
        ctx.ensure_return_write()
    assert info.value.code.value == "FORBIDDEN"


def test_shopper_return_write_ok() -> None:
    _ctx(UserRole.SHOPPER).ensure_return_write()


def test_conversation_read_matrix() -> None:
    _ctx(UserRole.SHOPPER).ensure_conversation_read()
    with pytest.raises(ToolError):
        _ctx(UserRole.SUPPORT, effective=uuid4()).ensure_conversation_read()
    _ctx(
        UserRole.SUPPORT,
        effective=uuid4(),
        permissions=("support:conversation:read",),
    ).ensure_conversation_read()
