from __future__ import annotations

from fastapi.testclient import TestClient


def test_chat_empty_request_rejected(client: TestClient):
    # Neither message nor image provided -> must return 400
    res = client.post("/chat", data={"message": "", "picker_id": "picker-123"})
    assert res.status_code == 400
    data = res.json()
    assert "Provide a message, an image, or both" in data["detail"]


def test_chat_v1_empty_request_rejected(client: TestClient):
    res = client.post("/api/v1/chat", data={"message": "", "picker_id": "picker-123"})
    assert res.status_code == 400
    data = res.json()
    assert "Provide a message, an image, or both" in data["detail"]
