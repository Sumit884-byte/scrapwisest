"""Step 10 regression tests: historical price trends & time-series integrity.

Observational layer only (no forecasting). Invariants:

- Source of truth is PriceReport.timestamp (naive -> UTC, never local).
- Only ACCEPTED reports contribute; PENDING/REJECTED never do.
- The current REPORT_FRESHNESS_DAYS window is NOT applied to history;
  an explicit [start, end] range selects the population instead.
- Market isolation via canonical market_key(country, currency); no conversion.
- Explicit scopes: neighborhood | city | country (no silent broadening).
- Daily aggregation over price_per_kg (never raw total_price).
- Seeds never create points; missing days stay missing.
- Empty history is points=[] with report_count=0 (no fabricated price).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.market import market_key
from app.schemas.report import MaterialType, PriceReport, ReportTrustStatus
from app.services.price_history import build_history, price_history_service

ALU = MaterialType.METAL_ALUMINUM
NOW = datetime(2026, 1, 31, 12, 0, 0, tzinfo=timezone.utc)


def _report(
    country="Pakistan",
    currency="PKR",
    city="Multan",
    neighborhood="Income Colony",
    price_per_kg=100.0,
    timestamp=NOW,
    trust=ReportTrustStatus.ACCEPTED,
    material=ALU,
    location=None,
    quantity_kg=2.0,
    total_price=None,
) -> PriceReport:
    total = total_price if total_price is not None else round(price_per_kg * quantity_kg, 2)
    return PriceReport(
        material_type=material,
        quantity_kg=quantity_kg,
        total_price=total,
        price_per_kg=price_per_kg,
        currency=currency,
        country=country,
        city=city,
        neighborhood=neighborhood,
        location=location if location is not None else (neighborhood or "unknown"),
        timestamp=timestamp,
        trust_status=trust,
    )


def _days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


def _history_pakistan(reports, **kw):
    kw.setdefault("currency", "PKR")
    kw.setdefault("country", "Pakistan")
    kw.setdefault("city", "Multan")
    kw.setdefault("neighborhood", "Income Colony")
    return build_history(ALU, reports, **kw)


# ---------------------------------------------------------------------------
# A. Basic historical series
# ---------------------------------------------------------------------------

def test_a_basic_series_multiple_days_ordered():
    reports = [
        _report(price_per_kg=100.0, timestamp=datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc)),
        _report(price_per_kg=200.0, timestamp=datetime(2026, 1, 12, 10, 0, tzinfo=timezone.utc)),
        _report(price_per_kg=300.0, timestamp=datetime(2026, 1, 11, 10, 0, tzinfo=timezone.utc)),
    ]
    trend = _history_pakistan(
        reports,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )
    assert trend.material_type == ALU
    assert trend.currency == "PKR"
    assert trend.country == "Pakistan"
    assert trend.scope == "neighborhood"
    assert trend.source == "reports"
    assert trend.report_count == 3
    assert [p.date for p in trend.points] == [
        date(2026, 1, 10),
        date(2026, 1, 11),
        date(2026, 1, 12),
    ]
    assert [p.average_price for p in trend.points] == [100.0, 300.0, 200.0]
    assert all(p.report_count == 1 for p in trend.points)


# ---------------------------------------------------------------------------
# B. Aggregation
# ---------------------------------------------------------------------------

def test_b_same_day_aggregation():
    ts = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    reports = [
        _report(price_per_kg=100.0, timestamp=ts),
        _report(price_per_kg=200.0, timestamp=ts + timedelta(hours=2)),
        _report(price_per_kg=300.0, timestamp=ts + timedelta(hours=5)),
    ]
    trend = _history_pakistan(
        reports, start_date=date(2026, 1, 1), end_date=date(2026, 1, 31)
    )
    assert len(trend.points) == 1
    point = trend.points[0]
    assert point.date == date(2026, 1, 15)
    assert point.report_count == 3
    assert point.average_price == round((100.0 + 200.0 + 300.0) / 3, 2) == 200.0
    assert point.min_price == 100.0
    assert point.max_price == 300.0
    assert point.median_price == 200.0
    assert trend.report_count == 3


# ---------------------------------------------------------------------------
# C. Per-unit pricing
# ---------------------------------------------------------------------------

def test_c_per_unit_not_total_price_averaging():
    day = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    # Report A: 10 kg -> 1000 PKR (100/kg); Report B: 100 kg -> 5000 PKR (50/kg).
    a = _report(
        price_per_kg=100.0, quantity_kg=10.0, total_price=1000.0, timestamp=day
    )
    b = _report(
        price_per_kg=50.0, quantity_kg=100.0, total_price=5000.0, timestamp=day
    )
    trend = _history_pakistan([a, b], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert len(trend.points) == 1
    # Must be (100+50)/2 = 75, never (1000+5000)/2 = 3000.
    assert trend.points[0].average_price == 75.0
    assert trend.points[0].average_price != 3000.0
    assert trend.points[0].report_count == 2


# ---------------------------------------------------------------------------
# D. Pending reports excluded
# ---------------------------------------------------------------------------

def test_d_pending_excluded():
    day = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    accepted = [_report(price_per_kg=100.0, timestamp=day)]
    pending = [
        _report(price_per_kg=999.0, timestamp=day, trust=ReportTrustStatus.PENDING)
        for _ in range(3)
    ]
    trend = _history_pakistan(
        accepted + pending, start_date=date(2026, 1, 1), end_date=date(2026, 1, 31)
    )
    assert trend.report_count == 1
    assert len(trend.points) == 1
    assert trend.points[0].average_price == 100.0


def test_d_only_pending_is_empty():
    day = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    pending = [_report(price_per_kg=999.0, timestamp=day, trust=ReportTrustStatus.PENDING)]
    trend = _history_pakistan(
        pending, start_date=date(2026, 1, 1), end_date=date(2026, 1, 31)
    )
    assert trend.points == []
    assert trend.report_count == 0


# ---------------------------------------------------------------------------
# E. Rejected reports excluded
# ---------------------------------------------------------------------------

def test_e_rejected_excluded():
    day = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    accepted = [_report(price_per_kg=100.0, timestamp=day)]
    rejected = [
        _report(price_per_kg=999.0, timestamp=day, trust=ReportTrustStatus.REJECTED)
        for _ in range(3)
    ]
    trend = _history_pakistan(
        accepted + rejected, start_date=date(2026, 1, 1), end_date=date(2026, 1, 31)
    )
    assert trend.report_count == 1
    assert trend.points[0].average_price == 100.0


# ---------------------------------------------------------------------------
# F. Historical stale reports (outside freshness window, inside range)
# ---------------------------------------------------------------------------

def test_f_stale_for_estimator_still_valid_history():
    assert settings.REPORT_FRESHNESS_DAYS == 30
    # 60 days old is stale for the current estimator but valid history
    # for a 90-day trend window.
    old_ts = NOW - timedelta(days=60)
    reports = [_report(price_per_kg=123.0, timestamp=old_ts)]
    trend = _history_pakistan(
        reports,
        start_date=(NOW - timedelta(days=90)).date(),
        end_date=NOW.date(),
    )
    assert trend.report_count == 1
    assert len(trend.points) == 1
    assert trend.points[0].average_price == 123.0


# ---------------------------------------------------------------------------
# G. Date range
# ---------------------------------------------------------------------------

def test_g_out_of_range_excluded():
    reports = [
        _report(price_per_kg=100.0, timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc)),
        _report(price_per_kg=200.0, timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc)),
        _report(price_per_kg=300.0, timestamp=datetime(2026, 1, 25, tzinfo=timezone.utc)),
    ]
    trend = _history_pakistan(
        reports, start_date=date(2026, 1, 10), end_date=date(2026, 1, 20)
    )
    assert trend.report_count == 1
    assert len(trend.points) == 1
    assert trend.points[0].date == date(2026, 1, 15)
    assert trend.points[0].average_price == 200.0


def test_g_range_bounds_inclusive():
    reports = [
        _report(price_per_kg=100.0, timestamp=datetime(2026, 1, 10, tzinfo=timezone.utc)),
        _report(price_per_kg=200.0, timestamp=datetime(2026, 1, 20, tzinfo=timezone.utc)),
    ]
    trend = _history_pakistan(
        reports, start_date=date(2026, 1, 10), end_date=date(2026, 1, 20)
    )
    assert trend.report_count == 2
    assert len(trend.points) == 2


# ---------------------------------------------------------------------------
# H. Market isolation
# ---------------------------------------------------------------------------

def test_h_markets_isolated():
    day = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    pool = [
        _report("Pakistan", "PKR", "Multan", "Income Colony", 500.0, timestamp=day),
        _report("India", "INR", "Delhi", "Karol Bagh", 500.0, timestamp=day),
        _report("United States", "USD", "Chicago", "Pilsen", 500.0, timestamp=day),
    ]
    pkr = build_history(
        ALU, pool, currency="PKR", country="Pakistan",
        city="Multan", neighborhood="Income Colony",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    inr = build_history(
        ALU, pool, currency="INR", country="India",
        city="Delhi", neighborhood="Karol Bagh",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    usd = build_history(
        ALU, pool, currency="USD", country="United States",
        city="Chicago", neighborhood="Pilsen",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    assert pkr.report_count == 1 and pkr.points[0].average_price == 500.0
    assert inr.report_count == 1 and inr.points[0].average_price == 500.0
    assert usd.report_count == 1 and usd.points[0].average_price == 500.0
    assert pkr.market_key() == ("PKR", "pakistan")
    assert inr.market_key() == ("INR", "india")
    assert usd.market_key() == ("USD", "united states")
    # Same nominal 500 in different currencies never pools: each scope sees 1.
    assert pkr.market_key() != inr.market_key() != usd.market_key()


def test_h_pkr_never_in_inr_series():
    day = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    pool = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, timestamp=day)]
    inr = build_history(
        ALU, pool, currency="INR", country="India",
        city="Delhi", neighborhood="Karol Bagh",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    assert inr.points == []
    assert inr.report_count == 0


# ---------------------------------------------------------------------------
# I. Currency normalization
# ---------------------------------------------------------------------------

def test_i_currency_normalization_same_market():
    day = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    reports = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, timestamp=day)]
    lower = build_history(
        ALU, reports, currency="pkr", country="Pakistan",
        city="Multan", neighborhood="Income Colony",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    upper = build_history(
        ALU, reports, currency="PKR", country="Pakistan",
        city="Multan", neighborhood="Income Colony",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    assert lower.currency == upper.currency == "PKR"
    assert lower.report_count == upper.report_count == 1
    assert lower.market_key() == upper.market_key() == ("PKR", "pakistan")
    assert market_key("Pakistan", "pkr") == ("PKR", "pakistan")


# ---------------------------------------------------------------------------
# J. Geographic isolation
# ---------------------------------------------------------------------------

def test_j_neighborhood_scope_strict():
    day = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    reports = [
        _report("Pakistan", "PKR", "Multan", "Income Colony", 100.0, timestamp=day),
        _report("Pakistan", "PKR", "Multan", "Samejabad", 999.0, timestamp=day, location="Samejabad"),
        _report("Pakistan", "PKR", "Multan", None, 999.0, timestamp=day, location="Multan"),
    ]
    trend = build_history(
        ALU, reports, currency="PKR", country="Pakistan",
        city="Multan", neighborhood="Income Colony",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    assert trend.scope == "neighborhood"
    assert trend.report_count == 1
    assert trend.points[0].average_price == 100.0


def test_j_neighborhood_same_name_different_city_isolated():
    day = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    reports = [
        _report("Pakistan", "PKR", "Multan", "Income Colony", 100.0, timestamp=day),
        _report("Pakistan", "PKR", "Lahore", "Income Colony", 999.0, timestamp=day),
    ]
    trend = build_history(
        ALU, reports, currency="PKR", country="Pakistan",
        city="Multan", neighborhood="Income Colony",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    assert trend.report_count == 1
    assert trend.points[0].average_price == 100.0


def test_j_city_scope_uses_city_pool_only():
    day = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    reports = [
        _report("Pakistan", "PKR", "Multan", "Income Colony", 100.0, timestamp=day),
        _report("Pakistan", "PKR", "Multan", "Samejabad", 200.0, timestamp=day, location="Samejabad"),
        _report("Pakistan", "PKR", "Lahore", "DHA", 999.0, timestamp=day, location="DHA"),
    ]
    trend = build_history(
        ALU, reports, currency="PKR", country="Pakistan", city="Multan",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    assert trend.scope == "city"
    assert trend.report_count == 2
    assert trend.points[0].average_price == 150.0
    assert trend.points[0].report_count == 2


def test_j_country_scope_uses_market_pool():
    day = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    reports = [
        _report("Pakistan", "PKR", "Multan", "Income Colony", 100.0, timestamp=day),
        _report("Pakistan", "PKR", "Lahore", "DHA", 200.0, timestamp=day, location="DHA"),
    ]
    trend = build_history(
        ALU, reports, currency="PKR", country="Pakistan",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    assert trend.scope == "country"
    assert trend.report_count == 2


# ---------------------------------------------------------------------------
# K. Seed exclusion
# ---------------------------------------------------------------------------

def test_k_seed_never_creates_history():
    # No reports at all, but a verified Pakistan/PKR seed exists (1050/kg).
    # History must be empty -- never the seed price.
    trend = _history_pakistan([], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert trend.points == []
    assert trend.report_count == 0
    assert trend.source == "reports"
    for point in trend.points:
        assert point.average_price != settings.SEED_PRICES["metal_aluminum"] or True
    # Explicit: no point may carry the seed value as implied observation when empty.
    assert trend.points == []


# ---------------------------------------------------------------------------
# L. Sparse history
# ---------------------------------------------------------------------------

def test_l_missing_days_stay_missing():
    reports = [
        _report(price_per_kg=100.0, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _report(price_per_kg=300.0, timestamp=datetime(2026, 1, 3, tzinfo=timezone.utc)),
        _report(price_per_kg=500.0, timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc)),
    ]
    trend = _history_pakistan(
        reports, start_date=date(2026, 1, 1), end_date=date(2026, 1, 5)
    )
    assert [p.date for p in trend.points] == [
        date(2026, 1, 1),
        date(2026, 1, 3),
        date(2026, 1, 5),
    ]
    # No zero / seed / forward-fill rows for Jan 2 and Jan 4.
    assert len(trend.points) == 3
    assert all(p.average_price != 0 for p in trend.points)
    assert trend.report_count == 3


# ---------------------------------------------------------------------------
# M. Chronological ordering
# ---------------------------------------------------------------------------

def test_m_sorted_oldest_to_newest():
    reports = [
        _report(price_per_kg=300.0, timestamp=datetime(2026, 1, 30, tzinfo=timezone.utc)),
        _report(price_per_kg=100.0, timestamp=datetime(2026, 1, 10, tzinfo=timezone.utc)),
        _report(price_per_kg=200.0, timestamp=datetime(2026, 1, 20, tzinfo=timezone.utc)),
    ]
    trend = _history_pakistan(
        reports, start_date=date(2026, 1, 1), end_date=date(2026, 1, 31)
    )
    dates = [p.date for p in trend.points]
    assert dates == sorted(dates)
    assert dates == [date(2026, 1, 10), date(2026, 1, 20), date(2026, 1, 30)]


# ---------------------------------------------------------------------------
# N. Empty history
# ---------------------------------------------------------------------------

def test_n_empty_history_no_fabrication():
    trend = build_history(
        ALU, [], currency="EUR", country="France", city="Paris",
        neighborhood="Le Marais",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    assert trend.points == []
    assert trend.report_count == 0
    assert trend.source == "reports"
    # Must not fall back to a current price or seed.
    assert trend.points == []


def test_n_no_history_despite_seed_market():
    # Pakistan/PKR has a verified seed; history with no reports is still empty.
    trend = _history_pakistan([], start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert trend.points == []
    assert trend.report_count == 0


# ---------------------------------------------------------------------------
# O. Trust + market + time matrix
# ---------------------------------------------------------------------------

def test_o_combined_constraints():
    in_day = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    out_day = datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc)
    reports = [
        # The single eligible report.
        _report("Pakistan", "PKR", "Multan", "Income Colony", 100.0, timestamp=in_day),
        # Wrong trust.
        _report("Pakistan", "PKR", "Multan", "Income Colony", 999.0, timestamp=in_day,
                trust=ReportTrustStatus.PENDING),
        _report("Pakistan", "PKR", "Multan", "Income Colony", 999.0, timestamp=in_day,
                trust=ReportTrustStatus.REJECTED),
        # Wrong market.
        _report("India", "INR", "Delhi", "Karol Bagh", 100.0, timestamp=in_day),
        _report("Pakistan", "PKR", "Multan", "Income Colony", 100.0, timestamp=in_day,
                material=MaterialType.GLASS),
        # Wrong scope (different neighborhood, same city/market).
        _report("Pakistan", "PKR", "Multan", "Samejabad", 100.0, timestamp=in_day,
                location="Samejabad"),
        # Wrong time (outside requested range).
        _report("Pakistan", "PKR", "Multan", "Income Colony", 100.0, timestamp=out_day),
    ]
    trend = _history_pakistan(
        reports, start_date=date(2026, 1, 1), end_date=date(2026, 1, 31)
    )
    assert trend.report_count == 1
    assert len(trend.points) == 1
    assert trend.points[0].average_price == 100.0


# ---------------------------------------------------------------------------
# Timezone handling: naive timestamps assumed UTC, aware ordered correctly
# ---------------------------------------------------------------------------

def test_timezone_naive_assumed_utc_not_local():
    naive = datetime(2026, 1, 15, 12, 0, 0)  # no tzinfo -> UTC
    reports = [_report(price_per_kg=100.0, timestamp=naive)]
    trend = _history_pakistan(
        reports, start_date=date(2026, 1, 15), end_date=date(2026, 1, 15)
    )
    assert trend.report_count == 1
    assert trend.points[0].date == date(2026, 1, 15)


def test_evidence_metadata():
    day = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    reports = [_report(price_per_kg=100.0, timestamp=day)]
    trend = _history_pakistan(
        reports, start_date=date(2026, 1, 1), end_date=date(2026, 1, 31)
    )
    assert trend.source == "reports"
    assert trend.currency == "PKR"
    assert trend.country == "Pakistan"
    assert trend.scope == "neighborhood"
    assert trend.start_date == date(2026, 1, 1)
    assert trend.end_date == date(2026, 1, 31)
    assert trend.market_key() == ("PKR", "pakistan")
    # No confidence concept on historical trends.
    assert not hasattr(trend, "confidence")


# ---------------------------------------------------------------------------
# API: GET /prices/history
# ---------------------------------------------------------------------------

def test_api_history_endpoint_returns_series():
    client = TestClient(app)
    res = client.get(
        "/api/v1/prices/history",
        params={
            "material": "metal_aluminum",
            "currency": "EUR",
            "country": "France",
            "city": "Paris",
            "neighborhood": "Le Marais",
            "start": "2026-01-01",
            "end": "2026-01-31",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["material_type"] == "metal_aluminum"
    assert data["currency"] == "EUR"
    assert data["scope"] == "neighborhood"
    assert data["source"] == "reports"
    assert data["points"] == []
    assert data["report_count"] == 0


def test_api_history_unknown_material_400():
    client = TestClient(app)
    res = client.get("/api/v1/prices/history", params={"material": "gold_dust"})
    assert res.status_code == 400


def test_api_history_invalid_range_400():
    client = TestClient(app)
    res = client.get(
        "/api/v1/prices/history",
        params={"material": "metal_aluminum", "start": "2026-02-01", "end": "2026-01-01"},
    )
    assert res.status_code == 400


def test_service_no_freshness_import_abuse():
    import pathlib

    here = pathlib.Path(__file__).resolve()
    # tests/unit/test_x.py -> parents[2] is backend/
    candidates = [
        here.parents[2] / "app" / "services" / "price_history.py",
        here.parents[1] / "app" / "services" / "price_history.py",
        pathlib.Path.cwd() / "app" / "services" / "price_history.py",
    ]
    src = next((p for p in candidates if p.exists()), candidates[0])
    text = src.read_text()
    # No functional use of the current-estimate freshness window (a docstring
    # mention explaining deliberate non-use is allowed).
    assert "filter_fresh_reports" not in text
    assert "is_report_fresh" not in text
    assert "settings.REPORT_FRESHNESS_DAYS" not in text
    assert "settings.report_freshness" not in text.lower()
    # Only timestamp normalization may be reused from report_freshness.
    assert "from app.services.report_freshness import _as_aware_utc" in text
    # Service must not import/call the estimator's current-price path
    # (a docstring mention explaining separation is allowed).
    assert "from app.services.price_estimator" not in text
    assert "import price_estimator" not in text
    assert "price_estimator_service" not in text
    assert "estimate(" not in text
    # Must not implement forecasting outputs (docstring may mention that
    # Step 11 will consume this layer later -- only code symbols matter).
    for forbidden in ("future_price", "next_week_price", "predicted_price", "trend_forecast"):
        assert forbidden not in text
    for forbidden_import in ("from prophet", "import prophet", "from statsmodels", "import xgboost", "from sklearn"):
        assert forbidden_import not in text.lower()
