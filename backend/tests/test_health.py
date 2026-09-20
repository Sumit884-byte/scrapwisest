def test_health_ok():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["models"]["provider"] == "nebius-token-factory"
