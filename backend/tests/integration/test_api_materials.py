from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_materials(client: TestClient):
    res = client.get("/api/v1/materials")
    assert res.status_code == 200
    data = res.json()
    assert "materials" in data
    assert data["count"] >= 8

    # Verify expected material fields
    pet = next((m for m in data["materials"] if m["id"] == "plastic_pet"), None)
    assert pet is not None
    assert pet["name_en"] == "PET plastic"
    assert "پلاسٹک" in pet["name_ur"]
    assert pet["seed_price_pkr_per_kg"] == 140.0
