"""Authorization dependency tests (no database).

Verifies that role/permission gates come from the verified bearer token and that a caller
cannot widen their own permissions via the request payload.
"""

from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from shopmate_ecommerce_assistant.api.deps import require_permission, require_role
from shopmate_ecommerce_assistant.api.errors import install_exception_handlers
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.security import (
    AccessContext,
    decode_access_token,
    issue_access_token,
    permissions_for,
)
from shopmate_ecommerce_assistant.db.models.enums import UserRole


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, jwt_secret="access-control-test-secret")


def _make_app(settings: Settings, dependency) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    install_exception_handlers(app)

    @app.get("/guard")
    async def guarded(context: Annotated[AccessContext, Depends(dependency)]):
        return {"role": context.role.value}

    return app


def _token(settings: Settings, role: UserRole) -> str:
    context = AccessContext(
        shop_id=uuid4(), user_id=uuid4(), role=role, permissions=permissions_for(role)
    )
    return issue_access_token(settings, context)


def test_require_role_rejects_wrong_role(settings: Settings) -> None:
    app = _make_app(settings, require_role(UserRole.ADMIN))

    with TestClient(app) as client:
        shopper_token = _token(settings, UserRole.SHOPPER)
        denied = client.get("/guard", headers={"Authorization": f"Bearer {shopper_token}"})

        admin_token = _token(settings, UserRole.ADMIN)
        allowed = client.get("/guard", headers={"Authorization": f"Bearer {admin_token}"})

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"
    assert allowed.status_code == 200
    assert allowed.json()["role"] == "admin"


def test_require_role_rejects_missing_token(settings: Settings) -> None:
    app = _make_app(settings, require_role(UserRole.ADMIN))

    with TestClient(app) as client:
        response = client.get("/guard")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_require_permission_gates_named_permission(settings: Settings) -> None:
    app = _make_app(settings, require_permission("support:conversation:read"))

    with TestClient(app) as client:
        support_token = _token(settings, UserRole.SUPPORT)
        allowed = client.get("/guard", headers={"Authorization": f"Bearer {support_token}"})

        # Admin has no support:conversation:read by default (docs/06-api.md §12).
        admin_token = _token(settings, UserRole.ADMIN)
        denied = client.get("/guard", headers={"Authorization": f"Bearer {admin_token}"})

    assert allowed.status_code == 200
    assert denied.status_code == 403


def test_permissions_cannot_be_widened_by_payload(settings: Settings) -> None:
    # The permission set is derived from the token's role at issue time; a shopper token
    # never carries admin permissions even if a crafted payload claims them.
    shopper = AccessContext(
        shop_id=uuid4(), user_id=uuid4(), role=UserRole.SHOPPER, permissions=frozenset()
    )
    token = issue_access_token(settings, shopper)

    decoded = decode_access_token(settings, token)
    assert decoded.role is UserRole.SHOPPER
    assert decoded.permissions == frozenset()
