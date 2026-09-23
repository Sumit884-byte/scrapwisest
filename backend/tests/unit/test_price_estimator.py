from __future__ import annotations

from datetime import datetime, timezone
import pytest

from app.schemas.report import MaterialType, PriceReport
from app.services.price_estimator import SEED_PRICES, estimate, estimate_price


def _report(material: MaterialType, location: str, price: float) -> PriceReport:
    return PriceReport(
        material_type=material,
        quantity_kg=2.0,
        price_paid_pkr=price * 2.0,
        price_paid_pkr_per_kg=price,
        location=location,
        timestamp=datetime.now(timezone.utc),
    )


def test_seed_fallback_when_no_reports():
    result = estimate(
        MaterialType.PLASTIC_PET,
        "income colony",
        [],
        currency="PKR",
        country="Pakistan",
    )
    assert result.tier_used == "seed"
    assert result.estimated_price_per_kg == SEED_PRICES[MaterialType.PLASTIC_PET]
    assert result.confidence == 0.20


def test_local_median_when_enough_neighborhood_reports():
    reports = [
        _report(MaterialType.PLASTIC_PET, "Income Colony", price)
        for price in (100.0, 120.0, 140.0, 160.0, 180.0)
    ]
    result = estimate(MaterialType.PLASTIC_PET, "income colony", reports)
    assert result.tier_used == "local"
    assert result.estimated_price_per_kg == 140.0
    assert result.local_report_count == 5


def test_unknown_material_is_an_error():
    out = estimate_price("banana_peel", "multan")
    assert isinstance(out, dict)
    assert "error" in out


def test_nemotron_routing_map():
    from app.agent.nemotron import routing_info

    info = routing_info()
    assert info["provider"] == "nebius-token-factory"
    assert "Nano" in info["fast"]["model"]
    assert "super" in info["everyday"]["model"]
    assert "Ultra" in info["reasoning"]["model"]


def test_active_provider_routing_map():
    """The dynamic router should return a valid routing map for whichever provider is active."""
    from app.agent.models import routing_info

    info = routing_info()
    assert "provider" in info
    assert info["provider"] in ("nebius-token-factory", "xkiro")
    assert "fast" in info and "model" in info["fast"]
    assert "everyday" in info and "model" in info["everyday"]
    assert "reasoning" in info and "model" in info["reasoning"]

