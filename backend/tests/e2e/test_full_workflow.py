from __future__ import annotations

from fastapi.testclient import TestClient


def test_full_platform_workflow(client: TestClient):
    # 1. Health check verifies service readiness
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    # 2. Material catalog lookup
    mats = client.get("/api/v1/materials")
    assert mats.status_code == 200
    mats_data = mats.json()
    assert mats_data["count"] > 0
    available_ids = [m["id"] for m in mats_data["materials"]]
    assert "plastic_hdpe" in available_ids

    # 3. Request scrap price estimate for plastic_hdpe
    est_res = client.get(
        "/api/v1/prices/estimate",
        params={"material": "plastic_hdpe", "location": "Samejabad"},
    )
    assert est_res.status_code == 200
    est = est_res.json()
    assert est["estimated_price_per_kg"] == 85.0  # Seed fallback

    # 4. Waste picker completes and submits sale report
    report_res = client.post(
        "/api/v1/reports",
        json={
            "material_type": "plastic_hdpe",
            "quantity_kg": 20.0,
            "total_price": 1700.0,  # 85 PKR / kg
            "currency": "PKR",
            "country": "Pakistan",
            "city": "Multan",
            "location": "Samejabad",
            "picker_id": "picker-workflow-01",
        },
    )
    assert report_res.status_code == 201
    rep = report_res.json()
    assert rep["price_per_kg"] == 85.0
    assert rep["currency"] == "PKR"

    # 5. Query updated reports to confirm data was saved
    query_res = client.get(
        "/api/v1/reports",
        params={"material": "plastic_hdpe", "location": "Samejabad"},
    )
    assert query_res.status_code == 200
    matching = query_res.json()
    assert any(r["picker_id"] == "picker-workflow-01" for r in matching)
