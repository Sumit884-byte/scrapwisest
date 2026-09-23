"""Step 2 regression tests: the estimator is market + location aware.

Pakistan/PKR, India/INR, and USA/USD reports must never pool together, city
filtering must be real (country + city, never city name alone), and seeds
must be market-specific (no PKR seed served as INR/USD).
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.market import market_key
from app.schemas.report import MaterialType, PriceReport
from app.services.location_resolver import normalize_location
from app.services.price_estimator import SEED_PRICES, estimate


def _report(
    country: str | None,
    currency: str,
    city: str | None,
    neighborhood: str,
    price_per_kg: float,
    material: MaterialType = MaterialType.METAL_ALUMINUM,
) -> PriceReport:
    return PriceReport(
        material_type=material,
        quantity_kg=2.0,
        total_price=round(price_per_kg * 2.0, 2),
        price_per_kg=price_per_kg,
        currency=currency,
        country=country,
        city=city,
        neighborhood=neighborhood,
        location=neighborhood,
        timestamp=datetime.now(timezone.utc),
    )


def _market_reports() -> list[PriceReport]:
    reports: list[PriceReport] = []
    reports += [
        _report("Pakistan", "PKR", "Multan", "Income Colony", 250.0)
        for _ in range(5)
    ]
    reports += [
        _report("India", "INR", "Delhi", "Karol Bagh", 35.0) for _ in range(5)
    ]
    reports += [
        _report("United States", "USD", "Chicago", "Pilsen", 1.0)
        for _ in range(5)
    ]
    return reports


def test_market_key_helper_covers_country_and_currency():
    assert market_key("Pakistan", "PKR") == ("PKR", "pakistan")
    assert market_key("India", "INR") == ("INR", "india")
    assert market_key("United States", "USD") == ("USD", "united states")
    assert market_key("Pakistan", "PKR") != market_key("India", "INR")


def test_normalize_location_keeps_city_only_usable():
    assert normalize_location("Multan") == "Multan"
    assert normalize_location("Multan") != ""


def test_market_isolation_three_markets():
    reports = _market_reports()

    pkr = estimate(
        MaterialType.METAL_ALUMINUM,
        "Income Colony",
        reports,
        currency="PKR",
        country="Pakistan",
        city="Multan",
        neighborhood="Income Colony",
    )
    assert pkr.currency == "PKR"
    assert pkr.estimated_price_per_kg == 250.0
    assert pkr.tier_used == "local"
    assert pkr.local_report_count == 5
    assert pkr.city_report_count == 5
    assert pkr.country_report_count == 5

    inr = estimate(
        MaterialType.METAL_ALUMINUM,
        "Karol Bagh",
        reports,
        currency="INR",
        country="India",
        city="Delhi",
        neighborhood="Karol Bagh",
    )
    assert inr.currency == "INR"
    assert inr.estimated_price_per_kg == 35.0
    assert inr.tier_used == "local"

    usd = estimate(
        MaterialType.METAL_ALUMINUM,
        "Pilsen",
        reports,
        currency="USD",
        country="United States",
        city="Chicago",
        neighborhood="Pilsen",
    )
    assert usd.currency == "USD"
    assert usd.estimated_price_per_kg == 1.0
    assert usd.tier_used == "local"


def test_pkr_reports_cannot_move_inr_or_usd_estimate():
    inr_only = [_report("India", "INR", "Delhi", "Karol Bagh", 35.0) for _ in range(5)]
    baseline = estimate(
        MaterialType.METAL_ALUMINUM,
        "Karol Bagh",
        inr_only,
        currency="INR",
        country="India",
        city="Delhi",
        neighborhood="Karol Bagh",
    )
    mixed = inr_only + [
        _report("Pakistan", "PKR", "Multan", "Income Colony", 500.0)
        for _ in range(10)
    ]
    with_pkr = estimate(
        MaterialType.METAL_ALUMINUM,
        "Karol Bagh",
        mixed,
        currency="INR",
        country="India",
        city="Delhi",
        neighborhood="Karol Bagh",
    )
    assert with_pkr.estimated_price_per_kg == baseline.estimated_price_per_kg == 35.0
    assert with_pkr.local_report_count == 5

    usd_only = [_report("United States", "USD", "Chicago", "Pilsen", 1.0) for _ in range(5)]
    usd_baseline = estimate(
        MaterialType.METAL_ALUMINUM,
        "Pilsen",
        usd_only,
        currency="USD",
        country="United States",
        city="Chicago",
        neighborhood="Pilsen",
    )
    usd_mixed = usd_only + [
        _report("Pakistan", "PKR", "Multan", "Income Colony", 500.0)
        for _ in range(10)
    ]
    usd_with_pkr = estimate(
        MaterialType.METAL_ALUMINUM,
        "Pilsen",
        usd_mixed,
        currency="USD",
        country="United States",
        city="Chicago",
        neighborhood="Pilsen",
    )
    assert usd_with_pkr.estimated_price_per_kg == usd_baseline.estimated_price_per_kg == 1.0


def test_city_isolation_same_country_currency():
    reports: list[PriceReport] = []
    reports += [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0) for _ in range(5)]
    reports += [_report("Pakistan", "PKR", "Multan", "Samejabad", 260.0) for _ in range(5)]
    reports += [_report("Pakistan", "PKR", "Lahore", "DHA", 500.0) for _ in range(10)]

    multan = estimate(
        MaterialType.METAL_ALUMINUM,
        "Multan",
        reports,
        currency="PKR",
        country="Pakistan",
        city="Multan",
    )
    lahore = estimate(
        MaterialType.METAL_ALUMINUM,
        "DHA",
        reports,
        currency="PKR",
        country="Pakistan",
        city="Lahore",
        neighborhood="DHA",
    )
    assert multan.currency == "PKR"
    assert lahore.currency == "PKR"
    # Multan city pool median of [250 x5, 260 x5] is 255, blended with the
    # Pakistan/PKR seed per the preserved city-tier formula:
    #   city_w = min(0.85, 10 / 20) = 0.5 -> 0.5 * 255 + 0.5 * 1050 = 652.5.
    # Lahore reports must not leak into the Multan pool (city count stays 10).
    assert multan.estimated_price_per_kg == 652.5
    assert multan.tier_used == "city"
    assert multan.city_report_count == 10
    assert multan.country_report_count == 20
    assert lahore.estimated_price_per_kg == 500.0


def test_neighborhood_isolation_same_name_different_cities():
    reports = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0) for _ in range(5)]
    reports += [_report("Pakistan", "PKR", "Lahore", "Income Colony", 500.0) for _ in range(5)]

    multan = estimate(
        MaterialType.METAL_ALUMINUM,
        "Income Colony",
        reports,
        currency="PKR",
        country="Pakistan",
        city="Multan",
        neighborhood="Income Colony",
    )
    lahore = estimate(
        MaterialType.METAL_ALUMINUM,
        "Income Colony",
        reports,
        currency="PKR",
        country="Pakistan",
        city="Lahore",
        neighborhood="Income Colony",
    )
    assert multan.estimated_price_per_kg == 250.0
    assert lahore.estimated_price_per_kg == 500.0
    assert multan.local_report_count == 5
    assert lahore.local_report_count == 5


def test_city_only_location_still_works():
    reports = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0) for _ in range(5)]
    result = estimate(
        MaterialType.METAL_ALUMINUM,
        "Multan",
        reports,
        currency="PKR",
        country="Pakistan",
        city="Multan",
    )
    assert result.currency == "PKR"
    assert result.estimated_price_per_kg > 0
    assert result.tier_used in ("city", "country", "local")


def test_country_fallback_tier_uses_market_reports():
    # Request targets a city with no reports (Karachi) while the wider
    # Pakistan/PKR market has depth. The city pool is empty, so the
    # country/market pool must serve the estimate -- never another market.
    reports = [_report("Pakistan", "PKR", "Multan", f"Multan Area {idx}", 250.0) for idx in range(5)]
    reports += [_report("Pakistan", "PKR", "Lahore", f"Lahore Area {idx}", 250.0) for idx in range(5)]
    result = estimate(
        MaterialType.METAL_ALUMINUM,
        "Somewhere New",
        reports,
        currency="PKR",
        country="Pakistan",
        city="Karachi",
        neighborhood="Somewhere New",
    )
    assert result.currency == "PKR"
    assert result.tier_used == "country"
    assert result.country_report_count == 10
    assert result.city_report_count == 0
    assert result.local_report_count == 0
    # Country median 250 blended with the Pakistan/PKR seed (1050):
    # country_w = min(0.85, 10 / 20) = 0.5 -> 650.0.
    assert result.estimated_price_per_kg == 650.0


def test_seed_isolation_pkr_seed_never_served_as_inr_or_usd():
    pkr_seed = SEED_PRICES[MaterialType.METAL_ALUMINUM]
    assert pkr_seed == 1050.0

    pakistan_empty = estimate(
        MaterialType.METAL_ALUMINUM,
        "Income Colony",
        [],
        currency="PKR",
        country="Pakistan",
        city="Multan",
        neighborhood="Income Colony",
    )
    assert pakistan_empty.tier_used == "seed"
    assert pakistan_empty.estimated_price_per_kg == pkr_seed
    assert pakistan_empty.currency == "PKR"

    india_empty = estimate(
        MaterialType.METAL_ALUMINUM,
        "Karol Bagh",
        [],
        currency="INR",
        country="India",
        city="Delhi",
        neighborhood="Karol Bagh",
    )
    assert india_empty.currency == "INR"
    assert india_empty.tier_used != "seed"
    assert india_empty.estimated_price_per_kg != pkr_seed

    usa_empty = estimate(
        MaterialType.METAL_ALUMINUM,
        "Pilsen",
        [],
        currency="USD",
        country="United States",
        city="Chicago",
        neighborhood="Pilsen",
    )
    assert usa_empty.currency == "USD"
    assert usa_empty.tier_used != "seed"
    assert usa_empty.estimated_price_per_kg != pkr_seed


def test_empty_market_returns_safe_no_estimate():
    result = estimate(
        MaterialType.METAL_ALUMINUM,
        "Le Marais",
        [],
        currency="EUR",
        country="France",
        city="Paris",
        neighborhood="Le Marais",
    )
    assert result.tier_used == "unavailable"
    assert result.confidence == 0.0
    assert result.estimated_price_per_kg == 0.0
    assert result.currency == "EUR"
    assert result.local_report_count == 0
    assert result.city_report_count == 0
    assert result.country_report_count == 0
