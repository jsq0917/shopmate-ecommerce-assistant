"""Trusted ``Host`` header enforcement (stage 14 production hardening).

The middleware is opt-in: ``TRUSTED_HOSTS`` is empty in local development so the existing
dev/e2e flows are unchanged, and compose.prod.yaml sets it to the public domain.

One regression case matters more than the rest: the compose healthcheck (and the
``docs/08`` verification commands) request ``http://127.0.0.1:8000/health`` from inside the
container, so ``127.0.0.1`` must be on the allow-list. When it is not, ``/health`` answers
400 and the container can never become healthy, which keeps ``web`` from starting at all.
"""

from fastapi.testclient import TestClient

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.main import create_app

# Same value as the production template: public domain *plus* loopback for the probe.
PROD_TRUSTED_HOSTS = "127.0.0.1,localhost,shopmate.example.invalid"


def _client(trusted_hosts: str, base_url: str) -> TestClient:
    settings = Settings(_env_file=None, trusted_hosts=trusted_hosts)
    return TestClient(create_app(settings=settings), base_url=base_url)


def test_trusted_host_is_accepted() -> None:
    with _client("shopmate.example.invalid", "https://shopmate.example.invalid") as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_untrusted_host_is_rejected() -> None:
    with _client("shopmate.example.invalid", "https://attacker.example.invalid") as client:
        response = client.get("/health")

    assert response.status_code == 400


def test_multiple_hosts_are_allowed() -> None:
    with _client(
        "shopmate.example.invalid, api.shopmate.example.invalid",
        "https://api.shopmate.example.invalid",
    ) as client:
        assert client.get("/health").status_code == 200


def test_empty_setting_keeps_host_check_disabled() -> None:
    with _client("", "http://testserver") as client:
        assert client.get("/health").status_code == 200


def test_loopback_probe_is_accepted_alongside_public_domain() -> None:
    """Container healthcheck (Host: 127.0.0.1) must pass with the production allow-list."""
    with _client(PROD_TRUSTED_HOSTS, "http://127.0.0.1:8000") as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_loopback_alias_localhost_is_accepted() -> None:
    with _client(PROD_TRUSTED_HOSTS, "http://localhost:8000") as client:
        assert client.get("/health").status_code == 200


def test_public_domain_still_accepted_with_probe_hosts_present() -> None:
    with _client(PROD_TRUSTED_HOSTS, "https://shopmate.example.invalid") as client:
        assert client.get("/health").status_code == 200


def test_attacker_host_rejected_with_probe_hosts_present() -> None:
    """Adding loopback to the allow-list must not turn Host validation into a no-op."""
    with _client(PROD_TRUSTED_HOSTS, "https://attacker.example.invalid") as client:
        response = client.get("/health")

    assert response.status_code == 400


def test_loopback_rejected_when_only_public_domain_allowed() -> None:
    """Guards the P1-1 regression itself: domain-only list breaks the in-container probe."""
    with _client("shopmate.example.invalid", "http://127.0.0.1:8000") as client:
        assert client.get("/health").status_code == 400
