"""Step 1 tests: the report data model is market-agnostic.

Pakistan/PKR, India/INR, and USA/USD reports must all coexist without any
country-specific schema changes, and 500 PKR must never equal 500 INR.
"""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.messages import HumanMessage

from app.agent.workflows.pipeline import validate_and_build
from app.schemas.market import (
    UNKNOWN_CURRENCY,
    is_plausible_currency,
    normalize_currency,
    normalize_place_part,
)
from app.schemas.report import MaterialType, PriceReport, RawExtraction
from app.services.location_resolver import (
    picker_currency_from_tags,
    picker_neighborhood_from_tags,
    picker_place_from_tags,
    validate_market_fields,
)
from app.services.price_estimator import estimate


def _report(
    country: str | None,
    currency: str | None,
    city: str | None,
    neighborhood: str,
    total: float,
    quantity: float,
) -> PriceReport:
    return PriceReport(
        material_type=MaterialType.METAL_ALUMINUM,
        quantity_kg=quantity,
        total_price=total,
        price_per_kg=round(total / quantity, 2),
        currency=currency or UNKNOWN_CURRENCY,
        country=country,
        city=city,
        neighborhood=neighborhood,
        location=neighborhood,
        timestamp=datetime.now(timezone.utc),
    )


def test_market_a_pakistan_pkr_multan():
    report = _report("Pakistan", "PKR", "Multan", "Income Colony", 5000.0, 20.0)
    assert report.price_per_kg == 250.0
    assert report.market_key() == ("PKR", "pakistan", "multan")

    dumped = report.model_dump()
    assert dumped["total_price"] == 5000.0
    assert dumped["currency"] == "PKR"
    assert dumped["country"] == "Pakistan"
    assert dumped["city"] == "Multan"
    assert dumped["neighborhood"] == "Income Colony"

    restored = PriceReport.model_validate_json(report.model_dump_json())
    assert restored.market_key() == ("PKR", "pakistan", "multan")


def test_market_b_india_inr_delhi():
    report = _report("India", "INR", "Delhi", "Karol Bagh", 700.0, 20.0)
    assert report.price_per_kg == 35.0
    assert report.market_key() == ("INR", "india", "delhi")


def test_market_c_usa_usd_chicago():
    report = _report("United States", "USD", "Chicago", "Pilsen", 20.0, 20.0)
    assert report.price_per_kg == 1.0
    assert report.market_key() == ("USD", "united states", "chicago")


def test_same_numbers_different_currencies_are_different_markets():
    pkr = _report("Pakistan", "PKR", "Multan", "Income Colony", 500.0, 5.0)
    inr = _report("India", "INR", "Delhi", "Karol Bagh", 500.0, 5.0)
    assert pkr.price_per_kg == inr.price_per_kg == 100.0
    assert pkr.market_key() != inr.market_key()
    assert {pkr.market_key(), inr.market_key()} == {
        ("PKR", "pakistan", "multan"),
        ("INR", "india", "delhi"),
    }


def test_reports_from_all_three_markets_store_side_by_side(tmp_path):
    from app.repositories.report_repository import ReportRepository

    repo = ReportRepository(tmp_path / "reports.db")
    markets = [
        ("Pakistan", "PKR", "Multan", "Income Colony", 5000.0, 20.0),
        ("India", "INR", "Delhi", "Karol Bagh", 700.0, 20.0),
        ("United States", "USD", "Chicago", "Pilsen", 20.0, 20.0),
    ]
    for country, currency, city, neighborhood, total, quantity in markets:
        repo.add(_report(country, currency, city, neighborhood, total, quantity))

    stored = repo.all_reports()
    assert len(stored) == 3
    assert {(r.currency, r.country, r.city) for r in stored} == {
        ("PKR", "Pakistan", "Multan"),
        ("INR", "India", "Delhi"),
        ("USD", "United States", "Chicago"),
    }


def test_legacy_kwargs_and_rows_still_parse_without_guessing():
    # Old constructor kwargs keep working (backwards compatibility).
    legacy = PriceReport(
        material_type=MaterialType.PLASTIC_PET,
        quantity_kg=5.0,
        price_paid_pkr=700.0,
        price_paid_pkr_per_kg=140.0,
        location="Gulgasht",
        timestamp=datetime.now(timezone.utc),
    )
    assert legacy.total_price == 700.0
    assert legacy.price_per_kg == 140.0
    # ... but nothing invents a currency for old data.
    assert legacy.currency == UNKNOWN_CURRENCY
    assert legacy.country is None
    assert legacy.city is None

    # Old stored JSON rows parse too, and serialize under the new names.
    old_json = (
        '{"material_type": "plastic_pet", "quantity_kg": 5.0, '
        '"price_paid_pkr": 700.0, "price_paid_pkr_per_kg": 140.0, '
        '"location": "Gulgasht"}'
    )
    parsed = PriceReport.model_validate_json(old_json)
    assert parsed.total_price == 700.0
    assert parsed.currency == UNKNOWN_CURRENCY
    assert '"total_price":700.0' in parsed.model_dump_json()


def test_raw_extraction_carries_structured_global_fields():
    raw = RawExtraction(
        material_type=MaterialType.METAL_ALUMINUM,
        material_confidence=0.9,
        quantity_kg=20.0,
        quantity_confidence=0.9,
        total_price=700.0,
        price_confidence=0.9,
        currency="INR",
        country="India",
        city="Delhi",
        neighborhood="Karol Bagh",
        location_text="Karol Bagh",
    )
    assert raw.currency == "INR"
    assert raw.city == "Delhi"

    # Legacy extraction key still accepted.
    legacy_raw = RawExtraction(
        material_type=MaterialType.METAL_ALUMINUM,
        material_confidence=0.9,
        quantity_kg=20.0,
        quantity_confidence=0.9,
        price_paid_pkr=5000.0,
        price_confidence=0.9,
    )
    assert legacy_raw.total_price == 5000.0
    assert legacy_raw.currency is None


def test_currency_and_place_normalization():
    assert normalize_currency(" pkr ") == "PKR"
    assert normalize_currency("inr") == "INR"
    assert normalize_currency(None) == UNKNOWN_CURRENCY
    assert normalize_currency("") == UNKNOWN_CURRENCY
    assert is_plausible_currency("USD")
    assert is_plausible_currency(UNKNOWN_CURRENCY)
    assert not is_plausible_currency("XYZ123")
    assert normalize_place_part("  Delhi  ") == "Delhi"
    assert normalize_place_part("   ") is None
    assert normalize_place_part(None) is None


def test_picker_context_tags_parse_deterministically():
    message = (
        "maine 20 kilo aluminum becha 5000 mein\n\n"
        "[picker_place: Multan, Pakistan]\n"
        "[picker_neighborhood: Income Colony]\n"
        "[picker_currency: PKR]"
    )
    assert picker_place_from_tags(message) == ("Multan", "Pakistan")
    assert picker_neighborhood_from_tags(message) == "Income Colony"
    assert picker_currency_from_tags(message) == "PKR"
    assert picker_place_from_tags("no tags here") == (None, None)
    assert picker_currency_from_tags("no tags here") is None
    assert picker_place_from_tags("[picker_place: Washington, D.C., United States]") == (
        "Washington",
        "D.C., United States",
    )


def test_validate_build_backfills_from_picker_tags():
    raw = RawExtraction(
        material_type=MaterialType.METAL_ALUMINUM,
        material_confidence=0.95,
        quantity_kg=5.0,
        quantity_confidence=0.95,
        total_price=5250.0,  # 1050/kg -- inside the legacy PKR band
        price_confidence=0.95,
        location_text=None,  # message named no place at all
    )
    state = {
        "raw_extraction": raw,
        "messages": [
            HumanMessage(
                content=(
                    "becha 5 kilo 5250 mein\n\n"
                    "[picker_place: Multan, Pakistan]\n"
                    "[picker_currency: PKR]"
                )
            )
        ],
    }
    result = validate_and_build(state)
    report = result["price_report"]
    assert report.needs_confirmation is False
    assert report.city == "Multan"
    assert report.country == "Pakistan"
    assert report.currency == "PKR"
    assert report.total_price == 5250.0
    assert report.price_per_kg == 1050.0


def test_unknown_extracted_currency_uses_picker_tag():
    raw = RawExtraction(
        material_type=MaterialType.METAL_ALUMINUM,
        material_confidence=0.95,
        quantity_kg=20.0,
        quantity_confidence=0.95,
        total_price=3200.0,
        price_confidence=0.95,
        currency="unknown",
        location_text=None,
    )
    result = validate_and_build(
        {
            "raw_extraction": raw,
            "messages": [
                HumanMessage(
                    content=(
                        "becha 20 kilo 3200 mein\n\n"
                        "[picker_place: Delhi, India]\n"
                        "[picker_currency: INR]"
                    )
                )
            ],
        }
    )
    report = result["price_report"]
    assert report.currency == "INR"
    assert report.city == "Delhi"
    assert report.country == "India"
    assert report.needs_confirmation is False


def test_validate_build_flags_bad_currency_without_guessing():
    raw = RawExtraction(
        material_type=MaterialType.PLASTIC_PET,
        material_confidence=0.95,
        quantity_kg=2.0,
        quantity_confidence=0.95,
        total_price=280.0,
        price_confidence=0.95,
        currency="XYZ123",
        location_text="Income Colony",
    )
    result = validate_and_build({"raw_extraction": raw})
    report = result["price_report"]
    assert report.needs_confirmation is True
    assert "unrecognized currency" in (report.confirmation_reason or "")


def test_validate_build_skips_legacy_band_for_other_currencies():
    # 1050/kg would pass the PKR band; as USD it must NOT be judged
    # against PKR-denominated bands.
    raw = RawExtraction(
        material_type=MaterialType.METAL_ALUMINUM,
        material_confidence=0.95,
        quantity_kg=5.0,
        quantity_confidence=0.95,
        total_price=5.5,
        price_confidence=0.95,
        currency="USD",
        country="USA",
        city="Chicago",
        location_text="Pilsen",
    )
    result = validate_and_build({"raw_extraction": raw})
    report = result["price_report"]
    assert report.needs_confirmation is False
    assert report.currency == "USD"
    assert report.country == "USA"
    assert report.city == "Chicago"
    assert report.price_per_kg == 1.1


def test_validate_market_fields_catches_long_place_names():
    reasons = validate_market_fields("INR", "India", "D" * 65, None)
    assert any("city" in reason for reason in reasons)
    assert validate_market_fields("INR", "India", "Delhi", "Karol Bagh") == []


def test_estimator_carries_currency_through():
    inr = _report("India", "INR", "Delhi", "Karol Bagh", 700.0, 20.0)
    result = estimate(
        MaterialType.METAL_ALUMINUM,
        "Karol Bagh",
        [inr],
        currency="INR",
        country="India",
        city="Delhi",
    )
    assert result.currency == "INR"
    assert result.estimated_price_per_kg > 0
    assert result.min_price_per_kg == 35.0

    pkr = _report("Pakistan", "PKR", "Multan", "Income Colony", 21000.0, 20.0)
    mixed = estimate(
        MaterialType.METAL_ALUMINUM,
        "Karol Bagh",
        [inr, pkr],
        currency="INR",
        country="India",
        city="Delhi",
    )
    assert mixed.city_report_count == 1
    assert mixed.max_price_per_kg == 35.0

    legacy = estimate(MaterialType.METAL_ALUMINUM, "Karol Bagh", [inr])
    assert legacy.currency == UNKNOWN_CURRENCY
