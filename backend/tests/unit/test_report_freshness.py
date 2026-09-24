"""Step 7 regression tests: report freshness & recency-aware market data.

Freshness rule (single implementation in app.services.report_freshness):

    fresh  <=>  timestamp >= now - REPORT_FRESHNESS_DAYS (inclusive)

Only fresh reports feed current estimates / anomaly populations. Seeds
never expire. No trust/reputation system is introduced here.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.schemas.report import MaterialType, PriceReport
from app.services.anomaly_detector import (
    _features,
    anomaly_detector_service,
    comparable_prices,
    comparable_reports,
    market_median_for,
    population_scope,
)
from app.services.price_estimator import SEED_PRICES, estimate
from app.services.report_freshness import (
    filter_fresh_reports,
    is_report_fresh,
)

ALU = MaterialType.METAL_ALUMINUM
NOW = datetime(2026, 1, 31, 12, 0, 0, tzinfo=timezone.utc)
FRESHNESS = 30  # matches settings.REPORT_FRESHNESS_DAYS default


def _report(
    country,
    currency,
    city,
    neighborhood,
    price_per_kg,
    timestamp=NOW,
    material=ALU,
    location=None,
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
        location=location if location is not None else (neighborhood or "unknown"),
        timestamp=timestamp,
    )


def _days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


# ---------------------------------------------------------------------------
# §14 -- freshness helper
# ---------------------------------------------------------------------------

def test_freshness_window_config_exists_and_default():
    assert settings.REPORT_FRESHNESS_DAYS == 30
    assert FRESHNESS == int(settings.REPORT_FRESHNESS_DAYS)


def test_fresh_report_within_window():
    assert is_report_fresh(_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, _days_ago(1)), now=NOW) is True
    assert is_report_fresh(_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, _days_ago(15)), now=NOW) is True
    # Spec example dates: 2026-01-30 and 2026-01-15 are fresh vs 2026-01-31.
    assert is_report_fresh(datetime(2026, 1, 30, 12, 0, tzinfo=timezone.utc), now=NOW) is True
    assert is_report_fresh(datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc), now=NOW) is True


def test_boundary_is_inclusive():
    # Exactly at the window edge (>= cutoff) counts as fresh.
    assert is_report_fresh(_days_ago(30), now=NOW, freshness_days=30) is True
    # One second older is stale.
    assert is_report_fresh(_days_ago(30) - timedelta(seconds=1), now=NOW, freshness_days=30) is False


def test_stale_report_beyond_window():
    assert is_report_fresh(_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, _days_ago(31)), now=NOW) is False
    assert is_report_fresh(datetime(2025, 12, 31, 12, 0, tzinfo=timezone.utc), now=NOW) is False


def test_future_timestamp_is_fresh_not_stale():
    # A slightly-future clock must not turn a current report ancient.
    future = NOW + timedelta(hours=1)
    assert is_report_fresh(_report("Pakistan", "PKR", "Multan", "X", 250.0, future), now=NOW) is True


def test_missing_timestamp_never_fresh():
    assert is_report_fresh(None, now=NOW) is False
    assert is_report_fresh("", now=NOW) is False

    class _NoTimestamp:
        timestamp = None

    assert is_report_fresh(_NoTimestamp(), now=NOW) is False
    # PriceReport with its timestamp wiped must also be stale, never "today".
    r = _report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, NOW)
    object.__setattr__(r, "timestamp", None)
    assert is_report_fresh(r, now=NOW) is False
    assert filter_fresh_reports([r], now=NOW) == []


def test_naive_datetime_assumed_utc_not_local():
    naive = datetime(2026, 1, 30, 12, 0, 0)  # no tzinfo -> assumed UTC
    assert is_report_fresh(naive, now=NOW) is True
    old_naive = datetime(2025, 12, 1, 12, 0, 0)
    assert is_report_fresh(old_naive, now=NOW) is False


def test_filter_preserves_order_and_counts_fresh_only():
    fresh = [_report("Pakistan", "PKR", "Multan", "A", 100.0, _days_ago(1)) for _ in range(5)]
    stale = [_report("Pakistan", "PKR", "Multan", "A", 999.0, _days_ago(60)) for _ in range(45)]
    out = filter_fresh_reports(fresh + stale, now=NOW)
    assert len(out) == 5
    assert all(r.price_per_kg == 100.0 for r in out)


# ---------------------------------------------------------------------------
# §15 -- estimator
# ---------------------------------------------------------------------------

def _estimate_pakistan(reports, **kw):
    kw.setdefault("now", NOW)
    return estimate(
        ALU, "Income Colony", reports,
        currency="PKR", country="Pakistan", city="Multan",
        neighborhood="Income Colony", **kw,
    )


def test_estimator_fresh_report_used():
    reports = [_report("Pakistan", "PKR", "Multan", "Income Colony", 100.0, _days_ago(2)) for _ in range(5)]
    res = _estimate_pakistan(reports)
    assert res.tier_used == "local"
    assert res.estimated_price_per_kg == 100.0
    assert res.local_report_count == 5


def test_estimator_stale_ignored_seed_fallback():
    stale = [_report("Pakistan", "PKR", "Multan", "Income Colony", 1000.0, _days_ago(90)) for _ in range(5)]
    res = _estimate_pakistan(stale)
    assert res.tier_used == "seed"
    assert res.estimated_price_per_kg == SEED_PRICES[ALU] == 1050.0
    assert res.local_report_count == 0
    assert res.city_report_count == 0
    assert res.country_report_count == 0


def test_estimator_fresh_beats_stale():
    fresh = [_report("Pakistan", "PKR", "Multan", "Income Colony", 100.0, _days_ago(1)) for _ in range(5)]
    stale = [_report("Pakistan", "PKR", "Multan", "Income Colony", 1000.0, _days_ago(120)) for _ in range(5)]
    res = _estimate_pakistan(fresh + stale)
    assert res.estimated_price_per_kg == 100.0
    assert res.tier_used == "local"
    assert res.local_report_count == 5  # stale excluded from counts


def test_estimator_stale_local_falls_back_to_fresh_city():
    stale_local = [_report("Pakistan", "PKR", "Multan", "Income Colony", 1000.0, _days_ago(90)) for _ in range(5)]
    fresh_city = [
        _report("Pakistan", "PKR", "Multan", "Samejabad", 100.0, _days_ago(2), location="Samejabad")
        for _ in range(10)
    ]
    res = _estimate_pakistan(stale_local + fresh_city)
    # Stale neighborhood must not anchor the estimate; city fallback wins.
    assert res.tier_used == "city"
    assert res.local_report_count == 0
    assert res.city_report_count == 10
    # City median 100 blended with seed 1050: 0.5*100 + 0.5*1050 = 575.
    assert res.estimated_price_per_kg == 575.0


def test_estimator_stale_everything_with_seed():
    stale = [_report("Pakistan", "PKR", "Multan", f"Area {i}", 999.0, _days_ago(200)) for i in range(10)]
    res = _estimate_pakistan(stale)
    assert res.tier_used == "seed"
    assert res.estimated_price_per_kg == SEED_PRICES[ALU]


def test_estimator_stale_everything_no_seed_unavailable():
    stale = [_report("India", "INR", "Delhi", "Karol Bagh", 999.0, _days_ago(200)) for _ in range(10)]
    res = estimate(
        ALU, "Karol Bagh", stale, currency="INR", country="India",
        city="Delhi", neighborhood="Karol Bagh", now=NOW,
    )
    assert res.tier_used == "unavailable"
    assert res.estimated_price_per_kg == 0.0
    assert res.confidence == 0.0


# ---------------------------------------------------------------------------
# §16 -- market isolation + freshness
# ---------------------------------------------------------------------------

def test_market_isolation_fresh_does_not_mix():
    reports = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, _days_ago(1)) for _ in range(5)]
    reports += [_report("India", "INR", "Delhi", "Karol Bagh", 35.0, _days_ago(1)) for _ in range(5)]
    pkr = _estimate_pakistan(reports)
    inr = estimate(
        ALU, "Karol Bagh", reports, currency="INR", country="India",
        city="Delhi", neighborhood="Karol Bagh", now=NOW,
    )
    assert pkr.estimated_price_per_kg == 250.0
    assert inr.estimated_price_per_kg == 35.0
    assert pkr.currency == "PKR" and inr.currency == "INR"


def test_stale_foreign_data_cannot_contaminate_fresh_market():
    fresh_inr = [_report("India", "INR", "Delhi", "Karol Bagh", 35.0, _days_ago(1)) for _ in range(5)]
    stale_pkr = [_report("Pakistan", "PKR", "Multan", "Income Colony", 500.0, _days_ago(200)) for _ in range(10)]
    res = estimate(
        ALU, "Karol Bagh", fresh_inr + stale_pkr, currency="INR", country="India",
        city="Delhi", neighborhood="Karol Bagh", now=NOW,
    )
    assert res.estimated_price_per_kg == 35.0
    assert res.local_report_count == 5


# ---------------------------------------------------------------------------
# §17 -- anomaly detection
# ---------------------------------------------------------------------------

def test_anomaly_uses_fresh_history_only():
    probe = _report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, NOW)
    fresh = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, _days_ago(2)) for _ in range(5)]
    stale = [_report("Pakistan", "PKR", "Multan", "Income Colony", 9999.0, _days_ago(200)) for _ in range(5)]
    prices = comparable_prices(probe, fresh + stale, now=NOW)
    assert prices == [250.0] * 5
    assert market_median_for(probe, fresh + stale, now=NOW) == 250.0
    assert population_scope(probe, fresh + stale, now=NOW) == "neighborhood"


def test_anomaly_stale_only_means_no_history():
    probe = _report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, NOW)
    stale = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, _days_ago(200)) for _ in range(5)]
    assert comparable_reports(probe, stale, now=NOW) == []
    assert comparable_prices(probe, stale, now=NOW) == []
    verdict = anomaly_detector_service.deterministic_check(probe, comparable_prices(probe, stale, now=NOW))
    assert verdict.is_anomalous is False
    assert "not enough regional history" in verdict.reason


def test_anomaly_tier1_thresholds_unchanged_with_fresh_median():
    probe = _report("Pakistan", "PKR", "Multan", "Income Colony", 100.0, NOW)
    history = comparable_prices(
        probe,
        [_report("Pakistan", "PKR", "Multan", "Income Colony", 100.0, _days_ago(1)) for _ in range(3)],
        now=NOW,
    )
    assert history == [100.0] * 3
    assert anomaly_detector_service.deterministic_check(probe, history).is_anomalous is False
    low = _report("Pakistan", "PKR", "Multan", "Income Colony", 49.0, NOW)
    assert anomaly_detector_service.deterministic_check(low, history).is_anomalous is True
    high = _report("Pakistan", "PKR", "Multan", "Income Colony", 201.0, NOW)
    assert anomaly_detector_service.deterministic_check(high, history).is_anomalous is True


def test_anomaly_tier2_features_unchanged_no_timestamp_feature():
    sig = inspect.signature(_features)
    assert list(sig.parameters) == ["price_per_kg", "quantity_kg", "material_median"]
    feat = _features(500.0, 2.0, 250.0)
    assert feat == [2.0, float(__import__("numpy").log1p(2.0))]
    assert len(feat) == 2
    import pathlib
    src = pathlib.Path("app/services/anomaly_detector.py").read_text()
    if not pathlib.Path("app/services/anomaly_detector.py").exists():
        src = pathlib.Path(__file__).resolve().parents[3] / "app" / "services" / "anomaly_detector.py"
        src = src.read_text()
    assert "days_old" not in src
    assert "city_id" not in src
    assert "country_id" not in src
