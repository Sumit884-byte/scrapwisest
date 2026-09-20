from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_price_estimate_valid(client: TestClient):
    res = client.get("/api/v1/prices/estimate", params={"material": "plastic_pet", "location": "Income Colony"})
    assert res.status_code == 200
    data = res.json()
    assert data["material_type"] == "plastic_pet"
    assert data["location"] == "Income Colony"
    assert data["estimated_price_per_kg"] > 0
    assert "tier_used" in data


def test_get_price_estimate_invalid_material(client: TestClient):
    res = client.get("/api/v1/prices/estimate", params={"material": "gold_dust", "location": "Multan"})
    assert res.status_code == 400
    data = res.json()
    assert "Unknown material" in data["detail"]
