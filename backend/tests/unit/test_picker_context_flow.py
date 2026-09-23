"""Step 3 regression tests: picker market/location context flows into reports.

Covers the nine required cases: no-location inheritance, explicit city
override, explicit different country/market, currency inheritance/override,
city-only picker, no picker context, direct API explicit values, and same
neighborhood name in different cities. At least some tests verify the final
saved repository object, not just intermediate extraction.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.agent.tool_outputs import begin, end, get_market_context, reset
from app.agent.workflows.pipeline import validate_and_build
from app.schemas.market import UNKNOWN_CURRENCY, MarketContext
from app.schemas.report import MaterialType, RawExtraction
from app.services.location_resolver import (
    resolve_market_context,
    validate_market_fields,
)


def _raw(
    country=None,
    currency=None,
    city=None,
    neighborhood=None,
    location_text=None,
    quantity_kg: float = 2.0,
    total_price: float = 300.0,  # 150/kg -- lower edge of the PKR aluminum band
) -> RawExtraction:
    return RawExtraction(
        material_type=MaterialType.METAL_ALUMINUM,
        material_confidence=0.95,
        quantity_kg=quantity_kg,
        quantity_confidence=0.95,
        total_price=total_price,
        price_confidence=0.95,
        currency=currency,
        country=country,
        city=city,
        neighborhood=neighborhood,
        location_text=location_text,
    )


def _msg(text: str) -> dict:
    return {"raw_extraction": None, "messages": [HumanMessage(content=text)]}


def _build(raw: RawExtraction, message_text: str):
    state = {"raw_extraction": raw, "messages": [HumanMessage(content=message_text)]}
    return validate_and_build(state)["price_report"]


# ---------------------------------------------------------------------------
# Test 1 -- No location in message inherits full picker context
# ---------------------------------------------------------------------------

def test_1_no_location_in_message_uses_picker():
    raw = _raw()  # message names no place or currency
    msg = (
        "I sold 2 kg aluminum for 300\n\n"
        "[picker_place: Multan, Pakistan]\n"
        "[picker_neighborhood: Income Colony]\n"
        "[picker_currency: PKR]"
    )
    report = _build(raw, msg)
    assert report.country == "Pakistan"
    assert report.currency == "PKR"
    assert report.city == "Multan"
    assert report.neighborhood == "Income Colony"
    assert report.location == "Income Colony"
    assert report.needs_confirmation is False

    # Pure resolver check mirrors the pipeline result.
    resolved = resolve_market_context(
        picker_country="Pakistan",
        picker_currency="PKR",
        picker_city="Multan",
        picker_neighborhood="Income Colony",
    )
    assert (resolved.country, resolved.currency, resolved.city, resolved.neighborhood) == (
        "Pakistan",
        "PKR",
        "Multan",
        "Income Colony",
    )


# ---------------------------------------------------------------------------
# Test 2 -- Explicit city override drops stale picker neighborhood
# ---------------------------------------------------------------------------

def test_2_explicit_city_override():
    raw = _raw(city="Lahore")  # user said Lahore; no country/currency stated
    msg = (
        "I sold it in Lahore for 300\n\n"
        "[picker_place: Multan, Pakistan]\n"
        "[picker_neighborhood: Income Colony]\n"
        "[picker_currency: PKR]"
    )
    report = _build(raw, msg)
    assert report.country == "Pakistan"
    assert report.currency == "PKR"
    assert report.city == "Lahore"
    # Income Colony belonged to Multan -- must not leak into Lahore.
    assert report.neighborhood is None
    assert report.city != "Multan"


# ---------------------------------------------------------------------------
# Test 3 -- Explicit different country/market has no picker contamination
# ---------------------------------------------------------------------------

def test_3_explicit_different_country_market():
    raw = _raw(country="India", currency="INR", city="Delhi", location_text="Karol Bagh")
    msg = (
        "I sold it in Delhi, India for 700 rupees INR\n\n"
        "[picker_place: Multan, Pakistan]\n"
        "[picker_currency: PKR]"
    )
    # Use an INR-plausible total (band check skipped for INR).
    raw.total_price = 700.0
    raw.quantity_kg = 2.0
    report = _build(raw, msg)
    assert report.country == "India"
    assert report.currency == "INR"
    assert report.city == "Delhi"
    assert report.country != "Pakistan"
    assert report.currency != "PKR"
    assert report.city != "Multan"

    # Country switch without an explicit currency must NOT inherit PKR
    # (avoids the obvious India/PKR inconsistency).
    fallback = resolve_market_context(
        explicit_country="India",
        explicit_city="Delhi",
        picker_country="Pakistan",
        picker_currency="PKR",
        picker_city="Multan",
        picker_neighborhood="Income Colony",
    )
    assert fallback.country == "India"
    assert fallback.city == "Delhi"
    assert fallback.currency == UNKNOWN_CURRENCY
    assert fallback.neighborhood is None


# ---------------------------------------------------------------------------
# Test 4 -- Currency inheritance from picker
# ---------------------------------------------------------------------------

def test_4_currency_inheritance():
    raw = _raw()  # "I sold aluminum for 500" -- no currency stated
    raw.total_price = 500.0
    msg = "I sold aluminum for 500\n\n[picker_place: Multan, Pakistan]\n[picker_currency: PKR]"
    report = _build(raw, msg)
    assert report.currency == "PKR"


# ---------------------------------------------------------------------------
# Test 5 -- Explicit currency override, no conversion
# ---------------------------------------------------------------------------

def test_5_explicit_currency_override_no_conversion():
    raw = _raw(currency="INR", quantity_kg=2.0, total_price=500.0)
    msg = "I sold aluminum for 500 INR\n\n[picker_place: Multan, Pakistan]\n[picker_currency: PKR]"
    report = _build(raw, msg)
    assert report.currency == "INR"
    # No conversion: totals pass through untouched.
    assert report.total_price == 500.0
    assert report.price_per_kg == 250.0


# ---------------------------------------------------------------------------
# Test 6 -- City-only picker setting
# ---------------------------------------------------------------------------

def test_6_city_only_picker_setting():
    raw = _raw()
    msg = "I sold 2 kg aluminum for 300\n\n[picker_place: Multan, Pakistan]\n[picker_currency: PKR]"
    report = _build(raw, msg)
    assert report.country == "Pakistan"
    assert report.currency == "PKR"
    assert report.city == "Multan"
    assert report.neighborhood is None


# ---------------------------------------------------------------------------
# Test 7 -- No picker context invents nothing
# ---------------------------------------------------------------------------

def test_7_no_picker_context_stays_unknown():
    raw = _raw()
    report = _build(raw, "I sold 2 kg aluminum for 300")
    assert report.currency == UNKNOWN_CURRENCY
    assert report.country is None
    assert report.city is None
    assert report.neighborhood is None
    # Must not default to Pakistan merely because the app started there.
    assert (report.country or "").lower() != "pakistan"

    empty = MarketContext()
    assert empty.is_empty() is True
    assert resolve_market_context().currency == UNKNOWN_CURRENCY


# ---------------------------------------------------------------------------
# Test 8 -- Direct API explicit values preserved exactly
# ---------------------------------------------------------------------------

def test_8_direct_api_explicit_values_preserved():
    # Unit-level: explicit payload values survive normalization untouched.
    from app.schemas.report import ReportCreate

    payload = ReportCreate(
        material_type=MaterialType.METAL_ALUMINUM,
        quantity_kg=2.0,
        total_price=700.0,
        currency="INR",
        country="India",
        city="Delhi",
        neighborhood="Karol Bagh",
        location="Karol Bagh",
    )
    assert payload.currency == "INR"
    assert payload.country == "India"
    assert payload.city == "Delhi"
    assert payload.neighborhood == "Karol Bagh"
    assert validate_market_fields("INR", "India", "Delhi", "Karol Bagh") == []


def test_8b_direct_reports_endpoint_preserves_india_inr(client, tmp_path, monkeypatch):
    # Isolated DB so this probe never pollutes backend/reports.db.
    from app.repositories.report_repository import ReportRepository, report_repo

    isolated = ReportRepository(tmp_path / "probe_reports.db")
    monkeypatch.setattr(report_repo, "db_path", isolated.db_path)
    payload = {
        "material_type": "metal_aluminum",
        "quantity_kg": 2.0,
        "total_price": 700.0,
        "currency": "INR",
        "country": "India",
        "city": "Delhi",
        "neighborhood": "Karol Bagh",
        "location": "Karol Bagh",
        "picker_id": "step3-direct-api-probe",
    }
    res = client.post("/api/v1/reports", json=payload)
    assert res.status_code == 201
    created = res.json()
    assert created["country"] == "India"
    assert created["currency"] == "INR"
    assert created["city"] == "Delhi"
    assert created["neighborhood"] == "Karol Bagh"
    assert created["location"] == "Karol Bagh"
    # Persistence verified in the isolated store as well.
    assert isolated.all_reports()[0].city == "Delhi"


# ---------------------------------------------------------------------------
# Test 9 -- Same neighborhood name, different city stays separated
# ---------------------------------------------------------------------------

def test_9_same_neighborhood_different_city():
    # Picker in Multan/Income Colony explicitly sells in Lahore: the saved
    # transaction must not keep Income Colony tied to Lahore.
    raw = _raw(city="Lahore")
    msg = (
        "sold in Lahore\n\n"
        "[picker_place: Multan, Pakistan]\n"
        "[picker_neighborhood: Income Colony]\n"
        "[picker_currency: PKR]"
    )
    report = _build(raw, msg)
    assert report.city == "Lahore"
    assert report.neighborhood is None

    # And a Multan/Income Colony report never becomes Lahore/Income Colony.
    multan = resolve_market_context(
        picker_country="Pakistan",
        picker_currency="PKR",
        picker_city="Multan",
        picker_neighborhood="Income Colony",
    )
    lahore = resolve_market_context(
        explicit_city="Lahore",
        picker_country="Pakistan",
        picker_currency="PKR",
        picker_city="Multan",
        picker_neighborhood="Income Colony",
    )
    assert multan.city == "Multan" and multan.neighborhood == "Income Colony"
    assert lahore.city == "Lahore" and lahore.neighborhood is None


# ---------------------------------------------------------------------------
# Persistence: message -> pipeline -> saved report carries context
# ---------------------------------------------------------------------------

def test_persistence_saved_report_carries_picker_context(tmp_path):
    from app.repositories.report_repository import ReportRepository

    raw = _raw()
    msg = (
        "I sold 2 kg aluminum for 300\n\n"
        "[picker_place: Multan, Pakistan]\n"
        "[picker_neighborhood: Income Colony]\n"
        "[picker_currency: PKR]"
    )
    report = _build(raw, msg)
    repo = ReportRepository(tmp_path / "reports.db")
    repo.add(report)
    saved = repo.all_reports()
    assert len(saved) == 1
    assert saved[0].country == "Pakistan"
    assert saved[0].currency == "PKR"
    assert saved[0].city == "Multan"
    assert saved[0].neighborhood == "Income Colony"
    assert saved[0].location == "Income Colony"


def test_persistence_explicit_override_saved(tmp_path):
    from app.repositories.report_repository import ReportRepository

    raw = _raw(country="India", currency="INR", city="Delhi", quantity_kg=2.0, total_price=700.0)
    msg = "Delhi India INR\n\n[picker_place: Multan, Pakistan]\n[picker_currency: PKR]"
    report = _build(raw, msg)
    repo = ReportRepository(tmp_path / "reports.db")
    repo.add(report)
    saved = repo.all_reports()[0]
    assert (saved.country, saved.currency, saved.city) == ("India", "INR", "Delhi")


def test_slot_fallback_survives_dropped_tags():
    """Even when the LLM's rewritten sentence drops [picker_*] tags, the
    per-request slot still supplies picker defaults to the pipeline."""
    reset()
    begin("slot-picker-1", {"country": "Pakistan", "currency": "PKR", "city": "Multan", "neighborhood": "Income Colony"})
    try:
        assert get_market_context("slot-picker-1")["city"] == "Multan"
        raw = _raw()  # no explicit place; message has NO tags (dropped)
        report = _build(raw, "I sold 2 kg aluminum for 300")
        assert report.country == "Pakistan"
        assert report.currency == "PKR"
        assert report.city == "Multan"
        assert report.neighborhood == "Income Colony"
    finally:
        end("slot-picker-1")
        reset()


def test_country_currency_mismatch_flagged_not_rewritten():
    reasons = validate_market_fields("PKR", "India", "Delhi", "Karol Bagh")
    assert any("mismatch" in r for r in reasons)

    raw = _raw(country="India", currency="PKR", city="Delhi", quantity_kg=2.0, total_price=700.0)
    report = _build(raw, "India PKR Delhi")
    # Values preserved raw; picker confirmation requested instead.
    assert report.country == "India"
    assert report.currency == "PKR"
    assert report.needs_confirmation is True
    assert "mismatch" in (report.confirmation_reason or "")


def test_ambiguous_location_preserves_picker():
    # "near the market" names no structured place -> picker context kept,
    # nothing invented.
    raw = _raw(location_text="near the market")
    msg = (
        "I sold it near the market\n\n"
        "[picker_place: Multan, Pakistan]\n"
        "[picker_currency: PKR]"
    )
    report = _build(raw, msg)
    assert report.country == "Pakistan"
    assert report.currency == "PKR"
    assert report.city == "Multan"


def test_estimator_uses_same_market_as_report():
    from app.schemas.report import PriceReport
    from app.services.price_estimator import price_estimator_service
    from datetime import datetime, timezone

    # Two isolated pools; the report's market must drive the estimate.
    pkr_report = PriceReport(
        material_type=MaterialType.METAL_ALUMINUM,
        quantity_kg=2.0,
        total_price=500.0,
        price_per_kg=250.0,
        currency="PKR",
        country="Pakistan",
        city="Multan",
        neighborhood="Income Colony",
        location="Income Colony",
        timestamp=datetime.now(timezone.utc),
    )
    est = price_estimator_service.estimate(
        MaterialType.METAL_ALUMINUM,
        pkr_report.neighborhood or pkr_report.location,
        reports=[pkr_report],
        currency=pkr_report.currency,
        country=pkr_report.country,
        city=pkr_report.city,
        neighborhood=pkr_report.neighborhood,
    )
    assert est.currency == "PKR"
