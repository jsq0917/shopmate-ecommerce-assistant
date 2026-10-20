"""Health and readiness endpoint tests."""

from fastapi.testclient import TestClient

from shopmate_ecommerce_assistant.main import create_app


class StubReadinessChecker:
    """Return a fixed readiness state."""

    def __init__(self, checks: dict[str, str] | None = None, *, fail: bool = False) -> None:
        self._checks = checks or {"postgres": "ok", "redis": "ok", "milvus": "ok"}
        self._fail = fail

    async def check(self) -> dict[str, str]:
        if self._fail:
            raise RuntimeError("postgresql://internal-user:secret@database/internal")
        return self._checks


def test_health_does_not_require_dependencies() -> None:
    app = create_app(readiness_checker=StubReadinessChecker(fail=True))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_200_when_all_dependencies_are_available() -> None:
    app = create_app(readiness_checker=StubReadinessChecker())

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"] == {
        "postgres": "ok",
        "redis": "ok",
        "milvus": "ok",
    }


def test_ready_returns_503_without_leaking_exception_details() -> None:
    app = create_app(readiness_checker=StubReadinessChecker(fail=True))

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"] == {"readiness": "error"}
    assert "postgresql://" not in response.text
    assert "secret" not in response.text


def test_ready_reports_partial_dependency_failure() -> None:
    app = create_app(
        readiness_checker=StubReadinessChecker({"postgres": "ok", "redis": "error", "milvus": "ok"})
    )

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["redis"] == "error"
