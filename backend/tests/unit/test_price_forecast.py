"""Step 11 regression tests: price forecasting foundation & forecast integrity.

Leakage-free baseline over Step 10 observational history. Invariants:

- Training data is ACCEPTED reports only, aggregated into daily buckets over
  ``price_per_kg`` (never raw ``total_price``). PENDING/REJECTED never train.
- Seeds NEVER train and never appear as points; a seed-only market forecasts
  ``no_history``, never the seed price.
- The current REPORT_FRESHNESS_DAYS window is NOT applied; the explicit
  FORECAST_TRAINING_WINDOW_DAYS window ending at the forecast origin is.
- Market isolation via canonical market_key(country, currency); no conversion.
- Explicit scopes: neighborhood | city | country (no silent broadening --
  unlike the current-price estimator, thin scopes return
  ``insufficient_history`` instead of borrowing a broader population).
- Chronological training (oldest -> newest); never reordered, strictly
  time-partitioned validation; no future observation ``> T`` ever trains.
- Deterministic moving-average baseline (mean of the most recent
  FORECAST_BASELINE_WINDOW observed daily averages); no ML dependencies, no
  persistent artifact; missing days stay missing (no fill).
- Statuses distinguish "no forecast" from zero prices: non-ready results are
  ``points=[]`` with ``horizon_days=0`` (never fabricated ``0.0`` points).
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.market import market_key
from app.schemas.report import MaterialType, PriceReport, ReportTrustStatus
from app.services.price_forecast import (
    MovingAverageBaseline,
    build_forecast,
    price_forecast_service,
)

ALU = MaterialType.METAL_ALUMINUM
NOW = datetime(2026, 1, 31, 12, 0, 0, tzinfo=timezone.utc)
SEED_ALU = settings.SEED_PRICES["metal_aluminum"]  # 1050.0 PKR, must never forecast


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


def _daily_series(
    prices,
    start: date,
    country="Pakistan",
    currency="PKR",
    city="Multan",
    neighborhood="Income Colony",
    trust=ReportTrustStatus.ACCEPTED,
    material=ALU,
) -> list[PriceReport]:
    reports = []
    for i, price in enumerate(prices):
        ts = datetime(start.year, start.month, start.day, 12, 0, tzinfo=timezone.utc) + timedelta(days=i)
        reports.append(
            _report(
                country=country,
                currency=currency,
                city=city,
                neighborhood=neighborhood,
                price_per_kg=price,
                timestamp=ts,
                trust=trust,
                material=material,
            )
        )
    return reports


def _forecast_pakistan(reports, **kw):
    kw.setdefault("currency", "PKR")
    kw.setdefault("country", "Pakistan")
    kw.setdefault("city", "Multan")
    kw.setdefault("neighborhood", "Income Colony")
    kw.setdefault("horizon_days", 3)
    return build_forecast(ALU, reports, **kw)


# ---------------------------------------------------------------------------
# Config sanity: minimum-history / horizon policy exists and is conservative
# ---------------------------------------------------------------------------

def test_config_forecast_policy_present():
    assert settings.FORECAST_MIN_POINTS >= 5
    assert settings.FORECAST_MIN_DAYS >= 3
    assert settings.FORECAST_BASELINE_WINDOW >= 2
    assert settings.FORECAST_BASELINE_WINDOW <= settings.FORECAST_MIN_POINTS
    assert settings.FORECAST_TRAINING_WINDOW_DAYS > settings.REPORT_FRESHNESS_DAYS
    assert 1 <= settings.FORECAST_HORIZON_DAYS <= settings.MAX_FORECAST_HORIZON_DAYS
    assert settings.MAX_FORECAST_HORIZON_DAYS <= 31
    assert settings.FORECAST_VALIDATION_POINTS >= 1


# ---------------------------------------------------------------------------
# A. Basic forecast
# ---------------------------------------------------------------------------

def test_a_basic_forecast_ready():
    prices = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0]
    reports = _daily_series(prices, date(2026, 1, 1))
    res = _forecast_pakistan(reports)
    assert res.status == "ready"
    assert res.material_type == ALU
    assert res.currency == "PKR"
    assert res.country == "Pakistan"
    assert res.scope == "neighborhood"
    assert res.source == "reports"
    assert res.model == "moving_average"
    # Baseline: mean of the most recent 3 observed daily averages.
    expected = round(statistics.fmean(prices[-3:]), 2)  # (140+150+160)/3 = 150
    assert expected == 150.0
    assert len(res.points) == 3
    assert [p.predicted_price for p in res.points] == [150.0, 150.0, 150.0]
    assert res.historical_start == date(2026, 1, 1)
    assert res.historical_end == date(2026, 1, 7)
    assert res.forecast_start == date(2026, 1, 8)
    assert res.forecast_end == date(2026, 1, 10)
    assert res.horizon_days == 3
    assert res.training_points == 7
    assert res.training_report_count == 7
    assert res.market_key() == ("PKR", "pakistan")


# ---------------------------------------------------------------------------
# B. No history
# ---------------------------------------------------------------------------

def test_b_no_history_empty():
    res = build_forecast(
        ALU, [], currency="EUR", country="France", city="Paris",
        neighborhood="Le Marais", horizon_days=3,
    )
    assert res.status == "no_history"
    assert res.points == []
    assert res.horizon_days == 0
    assert res.historical_start is None
    assert res.historical_end is None
    assert res.training_report_count == 0
    assert res.training_points == 0
    assert res.source == "reports"


# ---------------------------------------------------------------------------
# C. Insufficient history
# ---------------------------------------------------------------------------

def test_c_insufficient_history_too_few_points():
    reports = _daily_series([100.0, 110.0], date(2026, 1, 1))
    res = _forecast_pakistan(reports)
    assert res.status == "insufficient_history"
    assert res.points == []
    assert res.horizon_days == 0
    assert res.training_report_count == 0


def test_c_insufficient_history_below_minimums():
    # 4 daily buckets over 4 days (< MIN_POINTS and < MIN_DAYS).
    reports = _daily_series([100.0, 110.0, 120.0, 130.0], date(2026, 1, 1))
    res = _forecast_pakistan(reports)
    assert res.status == "insufficient_history"
    assert res.points == []


# ---------------------------------------------------------------------------
# D. Seed exclusion
# ---------------------------------------------------------------------------

def test_d_seed_only_market_has_no_forecast():
    # Pakistan/PKR has a verified seed (1050/kg) but zero historical reports:
    # the forecast must be no_history, never the seed price.
    res = _forecast_pakistan([])
    assert res.status == "no_history"
    assert res.points == []
    for point in res.points:
        assert point.predicted_price != SEED_ALU
    assert SEED_ALU == 1050.0  # guard: the seed we must never emit


def test_d_seed_value_never_trains():
    # Even when real history exists, the seed value must not leak into the
    # baseline: series avoids 1050 entirely and the forecast reflects only
    # observed prices.
    prices = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0]
    res = _forecast_pakistan(_daily_series(prices, date(2026, 1, 1)))
    assert res.status == "ready"
    assert all(p.predicted_price != SEED_ALU for p in res.points)
    assert all(p.predicted_price == 150.0 for p in res.points)


# ---------------------------------------------------------------------------
# E. Pending exclusion
# ---------------------------------------------------------------------------

def test_e_pending_cannot_train():
    accepted = _daily_series([100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0], date(2026, 1, 1))
    baseline = _forecast_pakistan(accepted)
    pending = _daily_series(
        [999.0] * 7, date(2026, 1, 1), trust=ReportTrustStatus.PENDING
    )
    res = _forecast_pakistan(accepted + pending)
    assert res.status == "ready"
    assert [p.predicted_price for p in res.points] == [p.predicted_price for p in baseline.points] == [150.0, 150.0, 150.0]
    assert res.training_report_count == 7


def test_e_only_pending_is_no_history():
    pending = _daily_series([999.0] * 7, date(2026, 1, 1), trust=ReportTrustStatus.PENDING)
    res = _forecast_pakistan(pending)
    assert res.status == "no_history"
    assert res.points == []


# ---------------------------------------------------------------------------
# F. Rejected exclusion
# ---------------------------------------------------------------------------

def test_f_rejected_cannot_train():
    accepted = _daily_series([100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0], date(2026, 1, 1))
    rejected = _daily_series(
        [999.0] * 7, date(2026, 1, 1), trust=ReportTrustStatus.REJECTED
    )
    res = _forecast_pakistan(accepted + rejected)
    assert res.status == "ready"
    assert [p.predicted_price for p in res.points] == [150.0, 150.0, 150.0]
    assert res.training_report_count == 7


def test_f_only_rejected_is_no_history():
    rejected = _daily_series([999.0] * 7, date(2026, 1, 1), trust=ReportTrustStatus.REJECTED)
    res = _forecast_pakistan(rejected)
    assert res.status == "no_history"
    assert res.points == []


# ---------------------------------------------------------------------------
# G. Market isolation
# ---------------------------------------------------------------------------

def test_g_markets_isolated():
    pool = []
    pool += _daily_series([100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0], date(2026, 1, 1))
    pool += _daily_series(
        [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0], date(2026, 1, 1),
        country="India", currency="INR", city="Delhi", neighborhood="Karol Bagh",
    )
    pool += _daily_series(
        [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6], date(2026, 1, 1),
        country="United States", currency="USD", city="Chicago", neighborhood="Pilsen",
    )
    pkr = _forecast_pakistan(pool)
    inr = build_forecast(
        ALU, pool, currency="INR", country="India", city="Delhi",
        neighborhood="Karol Bagh", horizon_days=3,
    )
    usd = build_forecast(
        ALU, pool, currency="USD", country="United States", city="Chicago",
        neighborhood="Pilsen", horizon_days=3,
    )
    assert pkr.status == inr.status == usd.status == "ready"
    assert [p.predicted_price for p in pkr.points] == [150.0] * 3
    assert [p.predicted_price for p in inr.points] == [15.0] * 3
    assert [p.predicted_price for p in usd.points] == [round(statistics.fmean([1.4, 1.5, 1.6]), 2)] * 3
    assert pkr.market_key() == ("PKR", "pakistan")
    assert inr.market_key() == ("INR", "india")
    assert usd.market_key() == ("USD", "united states")
    assert pkr.training_report_count == inr.training_report_count == usd.training_report_count == 7


def test_g_pkr_never_trains_inr_forecast():
    pool = _daily_series([250.0] * 7, date(2026, 1, 1))  # Pakistan/PKR only
    res = build_forecast(
        ALU, pool, currency="INR", country="India", city="Delhi",
        neighborhood="Karol Bagh", horizon_days=3,
    )
    assert res.status == "no_history"
    assert res.points == []


# ---------------------------------------------------------------------------
# H. Currency normalization
# ---------------------------------------------------------------------------

def test_h_currency_normalization_same_market():
    reports = _daily_series([100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0], date(2026, 1, 1))
    lower = build_forecast(
        ALU, reports, currency="pkr", country="Pakistan", city="Multan",
        neighborhood="Income Colony", horizon_days=3,
    )
    upper = build_forecast(
        ALU, reports, currency="PKR", country="Pakistan", city="Multan",
        neighborhood="Income Colony", horizon_days=3,
    )
    assert lower.currency == upper.currency == "PKR"
    assert lower.status == upper.status == "ready"
    assert [p.predicted_price for p in lower.points] == [p.predicted_price for p in upper.points]
    assert lower.market_key() == upper.market_key() == ("PKR", "pakistan")
    assert market_key("Pakistan", "pkr") == ("PKR", "pakistan")


# ---------------------------------------------------------------------------
# I. Geographic isolation (no silent broadening)
# ---------------------------------------------------------------------------

def test_i_neighborhood_scope_strict_no_broadening():
    # Requested neighborhood has only 2 observations; the SAME city holds 20
    # more in another neighborhood. Forecasting must NOT broaden to the city
    # pool -- the thin scope stays insufficient_history.
    thin = _daily_series([100.0, 110.0], date(2026, 1, 1))
    others = []
    for i in range(20):
        ts = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc) + timedelta(days=i % 7)
        others.append(
            _report(
                country="Pakistan", currency="PKR", city="Multan",
                neighborhood="Samejabad", price_per_kg=999.0,
                timestamp=ts, location="Samejabad",
            )
        )
    res = _forecast_pakistan(thin + others)
    assert res.scope == "neighborhood"
    assert res.status == "insufficient_history"
    assert res.points == []


def test_i_city_scope_uses_city_pool_only():
    reports = []
    for i, price in enumerate([100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0]):
        ts = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc) + timedelta(days=i)
        reports.append(_report(price_per_kg=price, timestamp=ts))
        reports.append(
            _report(
                country="Pakistan", currency="PKR", city="Multan",
                neighborhood="Samejabad", price_per_kg=price + 20.0,
                timestamp=ts, location="Samejabad",
            )
        )
    # Lahore data must not leak into the Multan city forecast.
    reports += _daily_series(
        [999.0] * 7, date(2026, 1, 1), country="Pakistan", currency="PKR",
        city="Lahore", neighborhood="DHA",
    )
    res = build_forecast(
        ALU, reports, currency="PKR", country="Pakistan", city="Multan",
        horizon_days=2,
    )
    assert res.scope == "city"
    assert res.status == "ready"
    # Daily averages: (p + p+20)/2 = p+10 -> last three: 150,160,170 -> 160.
    assert [p.predicted_price for p in res.points] == [160.0, 160.0]
    assert res.training_report_count == 14
    assert res.training_points == 7


def test_i_country_scope_uses_market_pool():
    reports = _daily_series([100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0], date(2026, 1, 1))
    reports += _daily_series(
        [200.0, 210.0, 220.0, 230.0, 240.0, 250.0, 260.0], date(2026, 1, 1),
        country="Pakistan", currency="PKR", city="Lahore", neighborhood="DHA",
    )
    res = build_forecast(
        ALU, reports, currency="PKR", country="Pakistan", horizon_days=2
    )
    assert res.scope == "country"
    assert res.status == "ready"
    # Daily market averages: 150..210 step 10 -> last three 190,200,210 -> 200.
    assert [p.predicted_price for p in res.points] == [200.0, 200.0]


# ---------------------------------------------------------------------------
# J. Historical freshness distinction
# ---------------------------------------------------------------------------

def test_j_stale_for_estimator_still_valid_forecast_history():
    assert settings.REPORT_FRESHNESS_DAYS == 30
    # 60 days old is stale for the current estimator but inside the
    # 180-day forecast training window -> valid training data.
    origin_day = (NOW - timedelta(days=60)).date()
    start_day = origin_day - timedelta(days=6)
    reports = _daily_series(
        [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0], start_day
    )
    res = _forecast_pakistan(reports)
    assert res.status == "ready"
    assert [p.predicted_price for p in res.points] == [150.0] * 3
    assert res.historical_end == origin_day
    assert res.training_report_count == 7


# ---------------------------------------------------------------------------
# K. Chronological ordering
# ---------------------------------------------------------------------------

def test_k_training_data_oldest_to_newest():
    prices = [160.0, 100.0, 140.0, 110.0, 150.0, 120.0, 130.0]
    days = [date(2026, 1, 7), date(2026, 1, 1), date(2026, 1, 5),
            date(2026, 1, 2), date(2026, 1, 6), date(2026, 1, 3), date(2026, 1, 4)]
    reports = [
        _report(price_per_kg=p, timestamp=datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc))
        for p, d in zip(prices, days)
    ]
    res = _forecast_pakistan(reports)
    assert res.status == "ready"
    assert res.historical_start == date(2026, 1, 1)
    assert res.historical_end == date(2026, 1, 7)
    # Sorted prices Jan1..Jan7: 100,110,120,130,140,150,160 -> baseline 150.
    assert [p.predicted_price for p in res.points] == [150.0] * 3
    forecast_dates = [p.date for p in res.points]
    assert forecast_dates == sorted(forecast_dates)
    assert forecast_dates == [date(2026, 1, 8), date(2026, 1, 9), date(2026, 1, 10)]


# ---------------------------------------------------------------------------
# L. No future leakage
# ---------------------------------------------------------------------------

def test_l_future_observations_cannot_influence_origin_forecast():
    past = _daily_series([100.0] * 7, date(2026, 1, 1))
    future = _daily_series([999.0] * 7, date(2026, 1, 20))
    res = _forecast_pakistan(past + future, end_date=date(2026, 1, 7))
    assert res.status == "ready"
    assert res.historical_end == date(2026, 1, 7)
    assert [p.predicted_price for p in res.points] == [100.0] * 3
    assert res.forecast_start == date(2026, 1, 8)


def test_l_origin_without_cap_uses_latest_observation():
    past = _daily_series([100.0] * 7, date(2026, 1, 1))
    future = _daily_series([200.0] * 7, date(2026, 1, 20))
    res = _forecast_pakistan(past + future)
    assert res.status == "ready"
    assert res.historical_end == date(2026, 1, 26)
    assert [p.predicted_price for p in res.points] == [200.0] * 3


# ---------------------------------------------------------------------------
# M. Time-based validation (chronological split)
# ---------------------------------------------------------------------------

def test_m_validation_is_chronological_holdout():
    prices = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0, 180.0]
    reports = _daily_series(prices, date(2026, 1, 1))
    res = _forecast_pakistan(reports)
    assert res.status == "ready"
    # Holdout: last 2 buckets (170, 180); prefix fit on last 3 of first 7
    # (140,150,160 -> 150); MAE = (|170-150| + |180-150|)/2 = 25.
    assert res.validation_points == settings.FORECAST_VALIDATION_POINTS == 2
    assert res.validation_mae == 25.0


def test_m_short_history_has_no_validation_score():
    # 5 buckets: enough to forecast (5 >= MIN_POINTS) but not enough for a
    # genuine holdout (needs MIN_POINTS + VALIDATION_POINTS = 7).
    reports = _daily_series([100.0, 110.0, 120.0, 130.0, 140.0], date(2026, 1, 1))
    res = _forecast_pakistan(reports)
    assert res.status == "ready"
    assert res.validation_mae is None
    assert res.validation_points == 0


# ---------------------------------------------------------------------------
# N. Baseline determinism
# ---------------------------------------------------------------------------

def test_n_same_input_same_forecast():
    reports = _daily_series([100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0], date(2026, 1, 1))
    first = _forecast_pakistan(reports)
    second = _forecast_pakistan(list(reports))
    assert first.model_dump() == second.model_dump()


def test_n_baseline_model_deterministic():
    model = MovingAverageBaseline(window=3)
    assert model.fit([1.0, 2.0, 3.0, 4.0]) == model.fit([1.0, 2.0, 3.0, 4.0]) == 3.0
    assert model.predict(3.0, 2) == [3.0, 3.0]


# ---------------------------------------------------------------------------
# O. Price unit (price_per_kg, never raw total_price)
# ---------------------------------------------------------------------------

def test_o_forecast_operates_on_price_per_kg():
    # Day arithmetic must use per-kg rates: (100 + 50)/2 = 75 for the shared
    # day, never (1000 + 5000)/2 = 3000.
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range(7)]
    reports = []
    for i, day in enumerate(days):
        ts = datetime(day.year, day.month, day.day, 12, 0, tzinfo=timezone.utc)
        if i == 6:
            reports.append(
                _report(price_per_kg=100.0, quantity_kg=10.0, total_price=1000.0, timestamp=ts)
            )
            reports.append(
                _report(price_per_kg=50.0, quantity_kg=100.0, total_price=5000.0, timestamp=ts + timedelta(hours=3))
            )
        else:
            reports.append(_report(price_per_kg=100.0, timestamp=ts))
    res = _forecast_pakistan(reports)
    assert res.status == "ready"
    # Daily averages: six days at 100, last day at 75 -> (100+100+75)/3.
    expected = round(statistics.fmean([100.0, 100.0, 75.0]), 2)
    assert expected == round(275.0 / 3, 2) == 91.67
    assert [p.predicted_price for p in res.points] == [expected] * 3
    assert all(p.predicted_price != 3000.0 for p in res.points)


# ---------------------------------------------------------------------------
# P. Sparse data (no silent fill)
# ---------------------------------------------------------------------------

def test_p_missing_days_not_filled():
    # 7 observations on alternate days (span 13 days): no zero/seed/fill rows.
    prices = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0]
    reports = []
    for i, price in enumerate(prices):
        day = date(2026, 1, 1) + timedelta(days=2 * i)
        reports.append(
            _report(
                price_per_kg=price,
                timestamp=datetime(day.year, day.month, day.day, 12, 0, tzinfo=timezone.utc),
            )
        )
    res = _forecast_pakistan(reports)
    assert res.status == "ready"
    assert res.training_points == 7  # only observed buckets, never filled days
    assert res.historical_start == date(2026, 1, 1)
    assert res.historical_end == date(2026, 1, 13)
    assert [p.predicted_price for p in res.points] == [150.0] * 3
    assert all(p.predicted_price != 0 for p in res.points)


# ---------------------------------------------------------------------------
# Q. Horizon validation
# ---------------------------------------------------------------------------

def test_q_invalid_horizons_rejected():
    reports = _daily_series([100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0], date(2026, 1, 1))
    for bad in (0, -1, settings.MAX_FORECAST_HORIZON_DAYS + 1, 365):
        res = _forecast_pakistan(reports, horizon_days=bad)
        assert res.status == "invalid_request", bad
        assert res.points == []
        assert res.horizon_days == 0


def test_q_unknown_material_invalid_request():
    res = build_forecast("gold_dust", [], currency="PKR", country="Pakistan")
    assert res.status == "invalid_request"
    assert res.points == []


def test_q_default_horizon_used_when_unspecified():
    reports = _daily_series([100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0], date(2026, 1, 1))
    res = build_forecast(
        ALU, reports, currency="PKR", country="Pakistan", city="Multan",
        neighborhood="Income Colony",
    )
    assert res.status == "ready"
    assert res.horizon_days == settings.FORECAST_HORIZON_DAYS
    assert len(res.points) == settings.FORECAST_HORIZON_DAYS


# ---------------------------------------------------------------------------
# R. Forecast evidence metadata
# ---------------------------------------------------------------------------

def test_r_evidence_metadata():
    prices = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0]
    reports = _daily_series(prices, date(2026, 1, 1))
    res = _forecast_pakistan(reports)
    assert res.status == "ready"
    assert res.model == "moving_average"
    assert res.source == "reports"
    assert res.historical_start == date(2026, 1, 1)
    assert res.historical_end == date(2026, 1, 7)
    assert res.training_report_count == 7
    assert res.training_points == 7
    assert res.currency == "PKR"
    assert res.country == "Pakistan"
    assert res.city == "Multan"
    assert res.neighborhood == "Income Colony"
    assert res.scope == "neighborhood"
    assert res.market_key() == ("PKR", "pakistan")
    # No fake confidence concept on forecasts.
    assert not hasattr(res, "confidence")


# ---------------------------------------------------------------------------
# S. Evaluation from a genuine chronological holdout
# ---------------------------------------------------------------------------

def test_s_mae_from_genuine_holdout_no_future_data():
    # Constant history: holdout error must be exactly zero.
    reports = _daily_series([120.0] * 9, date(2026, 1, 1))
    res = _forecast_pakistan(reports)
    assert res.status == "ready"
    assert res.validation_points == 2
    assert res.validation_mae == 0.0
    # The holdout days (Jan 8-9) are historical (<= origin Jan 9): shifting a
    # post-origin day cannot exist here, but moving a holdout price must move
    # MAE while the prefix fit stays based on earlier data only.
    shifted = _daily_series([120.0] * 7 + [150.0, 150.0], date(2026, 1, 1))
    res2 = _forecast_pakistan(shifted)
    assert res2.validation_points == 2
    # Prefix fit: last 3 of first 7 constant 120s -> 120; MAE = |150-120| = 30.
    assert res2.validation_mae == 30.0
    # The ready forecast itself uses all history <= origin
    # (last 3 buckets: 120, 150, 150 -> 140).
    assert [p.predicted_price for p in res2.points] == [140.0] * 3


# ---------------------------------------------------------------------------
# API: GET /prices/forecast
# ---------------------------------------------------------------------------

def test_api_forecast_endpoint_contract():
    client = TestClient(app)
    res = client.get(
        "/api/v1/prices/forecast",
        params={
            "material": "metal_aluminum",
            "currency": "EUR",
            "country": "France",
            "city": "Paris",
            "neighborhood": "Le Marais",
            "horizon_days": 3,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["material_type"] == "metal_aluminum"
    assert data["currency"] == "EUR"
    assert data["scope"] == "neighborhood"
    assert data["source"] == "reports"
    assert data["model"] == "moving_average"
    assert data["status"] == "no_history"
    assert data["points"] == []
    assert data["horizon_days"] == 0


def test_api_forecast_unknown_material_400():
    client = TestClient(app)
    res = client.get("/api/v1/prices/forecast", params={"material": "gold_dust"})
    assert res.status_code == 400


def test_api_forecast_invalid_horizon_400():
    client = TestClient(app)
    for bad in ("0", "-1", "99"):
        res = client.get(
            "/api/v1/prices/forecast",
            params={"material": "metal_aluminum", "horizon_days": bad},
        )
        assert res.status_code == 400, bad


def test_api_forecast_explicit_market_never_defaults():
    # No silent default to Pakistan/PKR and no cross-market inheritance: an
    # explicit foreign market with no history reports no_history (never the
    # Pakistan/PKR seed, never another market's data).
    client = TestClient(app)
    res = client.get(
        "/api/v1/prices/forecast",
        params={
            "material": "metal_aluminum",
            "currency": "INR",
            "country": "India",
            "city": "Delhi",
            "neighborhood": "Karol Bagh",
            "horizon_days": 3,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["currency"] == "INR"
    assert data["country"] == "India"
    assert data["status"] == "no_history"
    assert data["points"] == []
    assert data["horizon_days"] == 0


def test_service_backed_by_trusted_store_only():
    # Service defaults to trusted_reports(); trust is re-applied inside, so
    # even a store containing pending data cannot train.
    assert price_forecast_service is not None
    res = price_forecast_service.get_forecast(
        ALU, currency="EUR", country="France", city="Paris",
        neighborhood="Le Marais", horizon_days=3, reports=[],
    )
    assert res.status == "no_history"


# ---------------------------------------------------------------------------
# Leakage / unsafe-fallback audit: the forecast service must not touch seeds,
# current-estimate freshness, the estimator, or ML/random splitting.
# ---------------------------------------------------------------------------

def test_service_no_leakage_import_abuse():
    import pathlib

    here = pathlib.Path(__file__).resolve()
    candidates = [
        here.parents[2] / "app" / "services" / "price_forecast.py",
        here.parents[1] / "app" / "services" / "price_forecast.py",
        pathlib.Path.cwd() / "app" / "services" / "price_forecast.py",
    ]
    src = next((p for p in candidates if p.exists()), candidates[0])
    text = src.read_text(encoding="utf-8")
    # No functional use of the current-estimate freshness window (a docstring
    # mention explaining deliberate non-use is allowed).
    assert "filter_fresh_reports" not in text
    assert "is_report_fresh" not in text
    assert "settings.REPORT_FRESHNESS_DAYS" not in text
    assert "settings.report_freshness" not in text.lower()
    # Only history aggregation may be reused (trust/market/scope/range have
    # exactly one implementation); the estimator's current-price path is banned.
    assert "from app.services.price_history import build_history" in text
    assert "from app.services.price_estimator" not in text
    assert "import price_estimator" not in text
    assert "price_estimator_service" not in text
    # Seeds must never enter training (docstring mentions of exclusion ok).
    assert "SEED_PRICES" not in text
    assert "_seed_for" not in text
    assert "seed_price_for" not in text
    # No ML/random machinery: deterministic stdlib baseline only.
    assert "train_test_split" not in text
    assert "StandardScaler" not in text
    assert "MinMaxScaler" not in text
    assert "fit_transform" not in text
    assert ".transform(" not in text
    assert "from sklearn" not in text.lower()
    assert "import sklearn" not in text.lower()
    assert "import tensorflow" not in text.lower()
    assert "from tensorflow" not in text.lower()
    assert "import torch" not in text.lower()
    assert "from torch" not in text.lower()
    assert "from prophet" not in text.lower()
    assert "import prophet" not in text.lower()
    assert "from statsmodels" not in text.lower()
    assert "import xgboost" not in text.lower()
    # No chance-based partitioning of the time series.
    assert "import random" not in text
    assert "from random" not in text
    assert "random_state" not in text
    assert "np.random" not in text
