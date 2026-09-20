from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_api_v1(client: TestClient):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "models" in body
    assert body["models"]["provider"] == "nebius-token-factory"


def test_health_root_backward_compatible(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["models"]["provider"] == "nebius-token-factory"
