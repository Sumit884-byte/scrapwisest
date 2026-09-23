from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_and_list_reports(client: TestClient):
    # 1. Create a clean report (global market fields included)
    payload = {
        "material_type": "metal_aluminum",
        "quantity_kg": 10.0,
        "total_price": 10500.0,  # 1050 PKR / kg (well within 150-1500 band)
        "currency": "PKR",
        "country": "Pakistan",
        "city": "Multan",
        "neighborhood": "Shah Rukn-e-Alam",
        "location": "Shah Rukn-e-Alam",
        "picker_id": "test-picker-1",
    }
    create_res = client.post("/api/v1/reports", json=payload)
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["material_type"] == "metal_aluminum"
    assert created["price_per_kg"] == 1050.0
    assert created["total_price"] == 10500.0
    assert created["currency"] == "PKR"
    assert created["country"] == "Pakistan"
    assert created["city"] == "Multan"
    assert created["needs_confirmation"] is False

    # 2. Query reports
    list_res = client.get("/api/v1/reports", params={"material": "metal_aluminum"})
    assert list_res.status_code == 200
    reports = list_res.json()
    assert any(r["location"] == "Shah Rukn-e-Alam" for r in reports)
