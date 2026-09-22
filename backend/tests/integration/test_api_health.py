from __future__ import annotations

from fastapi.testclient import TestClient
from app.core.config import settings


def _expected_provider() -> str:
    """Return the provider string the health endpoint should report."""
    provider = (settings.LLM_PROVIDER or "xkiro").strip().lower()
    if provider in ("nebius", "nemotron", "nebius-token-factory"):
        return "nebius-token-factory"
    return "xkiro"


def test_health_api_v1(client: TestClient):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "models" in body
    assert body["models"]["provider"] == _expected_provider()


def test_health_root_backward_compatible(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["models"]["provider"] == _expected_provider()

