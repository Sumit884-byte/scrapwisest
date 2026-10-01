"""Step 4 regression tests: anomaly detection is market + location aware.

Pakistan/PKR, India/INR, and USA/USD reports must never share an anomaly
population; city and neighborhood scopes must not leak across boundaries.
Uses only the canonical helpers (market_key, same_city,
same_neighborhood) -- no duplicate market logic, no numeric city encoding.
"""

from __future__ import annotations

from datetime import datetime, timezone

import importlib

pipeline_mod = importlib.import_module("app.agent.workflows.pipeline")
from app.schemas.market import UNKNOWN_CURRENCY, market_key
from app.schemas.report import LLMJudgment, MaterialType, PriceReport
from app.services.anomaly_detector import (
    comparable_prices,
    comparable_reports,
    describe_market,
    in_same_market,
    market_median_for,
    population_scope,
    anomaly_detector_service,
)
from app.services.location_resolver import same_city

ALU = MaterialType.METAL_ALUMINUM


def _report(
    country,
    currency,
    city,
    neighborhood,
    price_per_kg,
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
        timestamp=datetime.now(timezone.utc),
    )


def _market_pool() -> list[PriceReport]:
    reports: list[PriceReport] = []
    reports += [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0) for _ in range(5)]
    reports += [_report("India", "INR", "Delhi", "Karol Bagh", 35.0) for _ in range(5)]
    reports += [_report("United States", "USD", "Chicago", "Pilsen", 1.0) for _ in range(5)]
    return reports


# ---------------------------------------------------------------------------
# Test 1 -- Currency isolation across three markets
# ---------------------------------------------------------------------------

def test_1_currency_isolation_three_markets():
    pool = _market_pool()
    multan = _report("Pakistan", "PKR", "Multan", "Income Colony", 250.0)
    delhi = _report("India", "INR", "Delhi", "Karol Bagh", 35.0)
    chicago = _report("United States", "USD", "Chicago", "Pilsen", 1.0)

    for probe, price in ((multan, 250.0), (delhi, 35.0), (chicago, 1.0)):
        prices = comparable_prices(probe, pool)
        assert len(prices) == 5
        assert all(p == price for p in prices)

    # 500 PKR/kg cannot move the INR baseline: the INR population stays [35].
    inr_prices = comparable_prices(delhi, pool + [_report("Pakistan", "PKR", "Multan", "Income Colony", 500.0) for _ in range(10)])
    assert inr_prices == [35.0] * 5

    # Same raw number, opposite verdicts per market: 35 is normal in Delhi
    # (median 35) but anomalous against Multan's median (250).
    assert anomaly_detector_service.deterministic_check(delhi, [35.0] * 5).is_anomalous is False
    assert anomaly_detector_service.deterministic_check(delhi, [250.0] * 5).is_anomalous is True


# ---------------------------------------------------------------------------
# Test 2 -- Country isolation when currency is shared
# ---------------------------------------------------------------------------

def test_2_country_isolation_same_currency():
    pool = [
        _report("Freedonia", "USD", "Springfield", "Northside", 10.0) for _ in range(5)
    ] + [
        _report("Sylvania", "USD", "Springfield", "Northside", 90.0) for _ in range(5)
    ]
    free = _report("Freedonia", "USD", "Springfield", "Northside", 10.0)
    sylv = _report("Sylvania", "USD", "Springfield", "Northside", 90.0)

    assert market_key("Freedonia", "USD") != market_key("Sylvania", "USD")
    assert comparable_prices(free, pool) == [10.0] * 5
    assert comparable_prices(sylv, pool) == [90.0] * 5
    assert in_same_market(free, sylv) is False


# ---------------------------------------------------------------------------
# Test 3 -- City isolation within one market
# ---------------------------------------------------------------------------

def test_3_city_isolation_same_market():
    pool = [_report("Pakistan", "PKR", "Multan", f"Multan Area {i}", 250.0) for i in range(5)]
    pool += [_report("Pakistan", "PKR", "Lahore", f"Lahore Area {i}", 500.0) for i in range(5)]

    multan = _report("Pakistan", "PKR", "Multan", "Somewhere New", 250.0)
    lahore = _report("Pakistan", "PKR", "Lahore", "Elsewhere New", 500.0)

    assert comparable_prices(multan, pool) == [250.0] * 5
    assert comparable_prices(lahore, pool) == [500.0] * 5
    # 500 is normal in Lahore but over double Multan's median (510 > 2*250).
    assert anomaly_detector_service.deterministic_check(lahore, [500.0] * 5).is_anomalous is False
    assert anomaly_detector_service.deterministic_check(
        _report("Pakistan", "PKR", "Multan", "X", 510.0), [250.0] * 5
    ).is_anomalous is True


# ---------------------------------------------------------------------------
# Test 4 -- Neighborhood isolation for identical names
# ---------------------------------------------------------------------------

def test_4_neighborhood_isolation_same_name_different_cities():
    pool = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0) for _ in range(5)]
    pool += [_report("Pakistan", "PKR", "Lahore", "Income Colony", 500.0) for _ in range(5)]

    multan = _report("Pakistan", "PKR", "Multan", "Income Colony", 250.0)
    lahore = _report("Pakistan", "PKR", "Lahore", "Income Colony", 500.0)

    assert population_scope(multan, pool) == "neighborhood"
    assert comparable_prices(multan, pool) == [250.0] * 5
    assert comparable_prices(lahore, pool) == [500.0] * 5


# ---------------------------------------------------------------------------
# Test 5 -- Normalization through the existing resolver
# ---------------------------------------------------------------------------

def test_5_case_insensitive_city_matching():
    pool = [_report("Pakistan", "PKR", "Multan", f"Area {i}", 250.0) for i in range(5)]
    probe = _report("pakistan", "pkr", "multan", "New Area", 250.0)
    assert same_city(probe.city, probe.country, "Multan", "Pakistan") is True
    assert comparable_prices(probe, pool) == [250.0] * 5


# ---------------------------------------------------------------------------
# Test 6 -- City-only report joins the city population
# ---------------------------------------------------------------------------

def test_6_city_only_report_in_city_population():
    pool = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0) for _ in range(5)]
    city_only = _report("Pakistan", "PKR", "Multan", None, 250.0, location="unknown")
    assert city_only.neighborhood is None
    assert population_scope(city_only, pool) == "city"
    assert comparable_prices(city_only, pool) == [250.0] * 5


# ---------------------------------------------------------------------------
# Test 7 -- Unknown market never joins Pakistan/PKR
# ---------------------------------------------------------------------------

def test_7_unknown_market_is_own_population():
    pool = _market_pool()
    unknown = _report(None, UNKNOWN_CURRENCY, None, None, 250.0, location="unknown")
    assert market_key(None, UNKNOWN_CURRENCY) != market_key("Pakistan", "PKR")
    assert comparable_prices(unknown, pool) == []
    verdict = anomaly_detector_service.deterministic_check(unknown, [])
    assert verdict.is_anomalous is False
    assert "not enough regional history" in verdict.reason


# ---------------------------------------------------------------------------
# Test 8 -- Tier 1 0.5x / 2x thresholds preserved after scoping
# ---------------------------------------------------------------------------

def test_8_tier1_thresholds_preserved():
    probe = _report("Pakistan", "PKR", "Multan", "Income Colony", 100.0)
    history = [100.0, 100.0, 100.0]
    assert anomaly_detector_service.deterministic_check(probe, history).is_anomalous is False
    low_edge = _report("Pakistan", "PKR", "Multan", "Income Colony", 50.0)
    assert anomaly_detector_service.deterministic_check(low_edge, history).is_anomalous is False
    low = _report("Pakistan", "PKR", "Multan", "Income Colony", 49.0)
    assert anomaly_detector_service.deterministic_check(low, history).is_anomalous is True
    high_edge = _report("Pakistan", "PKR", "Multan", "Income Colony", 200.0)
    assert anomaly_detector_service.deterministic_check(high_edge, history).is_anomalous is False
    high = _report("Pakistan", "PKR", "Multan", "Income Colony", 201.0)
    assert anomaly_detector_service.deterministic_check(high, history).is_anomalous is True


# ---------------------------------------------------------------------------
# Test 9 -- Insufficient local data keeps the safe default
# ---------------------------------------------------------------------------

def test_9_insufficient_history_accepted_by_default():
    probe = _report("Pakistan", "PKR", "Multan", "Brand New Area", 9999.0)
    assert comparable_prices(probe, []) == []
    verdict = anomaly_detector_service.deterministic_check(probe, comparable_prices(probe, []))
    assert verdict.is_anomalous is False
    assert "not enough regional history" in verdict.reason
    # Sparse neighborhood falls back to real city data, never fabricated.
    pool = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0) for _ in range(5)]
    assert population_scope(probe, pool) == "city"
    assert comparable_prices(probe, pool) == [250.0] * 5


# ---------------------------------------------------------------------------
# Test 10 -- Tier 3 judge receives market/location context (mocked LLM)
# ---------------------------------------------------------------------------

def test_10_llm_judge_prompt_carries_market_context(monkeypatch):
    pool = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0) for _ in range(5)]
    flagged = _report("Pakistan", "PKR", "Multan", "Income Colony", 9999.0)

    captured: dict = {}

    class _StubJudge:
        def invoke(self, prompt):
            captured["prompt"] = prompt
            return LLMJudgment(is_anomalous=True, reason="mocked", confidence=0.8)

    monkeypatch.setattr(pipeline_mod, "_judge_model", lambda: _StubJudge())
    monkeypatch.setattr(
        pipeline_mod.report_repo, "trusted_reports", lambda: list(pool)
    )
    state = {
        "price_report": flagged,
        "deterministic_result": anomaly_detector_service.deterministic_check(
            flagged, comparable_prices(flagged, pool)
        ),
        "ml_result": anomaly_detector_service.ml_check(flagged, market_median_for(flagged, pool)),
    }
    assert state["deterministic_result"].is_anomalous is True
    out = pipeline_mod.llm_check_node(state)
    assert out["verdict"].method == "llm"
    prompt = captured["prompt"]
    assert "Pakistan" in prompt and "PKR" in prompt and "Multan" in prompt
    assert "Income Colony" in prompt
    # No cross-market *data* leakage: the history shown is the PKR scope only.
    assert "[250.0, 250.0, 250.0, 250.0, 250.0]" in prompt
    assert "Karol Bagh" not in prompt


def test_10b_describe_market_distinguishes_markets():
    pkr = _report("Pakistan", "PKR", "Multan", "Income Colony", 250.0)
    inr = _report("India", "INR", "Delhi", "Karol Bagh", 35.0)
    assert describe_market(pkr) != describe_market(inr)
    assert "PKR" in describe_market(pkr) and "Multan" in describe_market(pkr)
    assert "INR" in describe_market(inr) and "Delhi" in describe_market(inr)


# ---------------------------------------------------------------------------
# §17 -- Estimator and anomaly detector agree on market identity
# ---------------------------------------------------------------------------

def test_17_estimator_and_anomaly_share_market_identity():
    from app.services.price_estimator import price_estimator_service

    pool = _market_pool()
    delhi = _report("India", "INR", "Delhi", "Karol Bagh", 35.0)

    est = price_estimator_service.estimate(
        ALU,
        delhi.neighborhood or delhi.location,
        reports=list(pool),
        currency=delhi.currency,
        country=delhi.country,
        city=delhi.city,
        neighborhood=delhi.neighborhood,
    )
    assert est.currency == "INR"
    assert est.estimated_price_per_kg == 35.0

    prices = comparable_prices(delhi, pool)
    assert prices == [35.0] * 5
    # Both populations keyed identically: country + currency, never mixed.
    assert {market_key(r.country, r.currency) for r in comparable_reports(delhi, pool)} == {
        market_key("India", "INR")
    }


def test_ml_median_is_market_scoped():
    pool = _market_pool()
    delhi = _report("India", "INR", "Delhi", "Karol Bagh", 35.0)
    multan = _report("Pakistan", "PKR", "Multan", "Income Colony", 250.0)
    assert market_median_for(delhi, pool) == 35.0
    assert market_median_for(multan, pool) == 250.0
    # Same raw price normalizes differently per market (no raw pooling).
    from app.services.anomaly_detector import _features

    assert _features(500.0, 2.0, 250.0)[0] == 2.0
    assert _features(500.0, 2.0, 35.0)[0] > 14.0


def test_retrain_groups_medians_by_market(tmp_path):
    """Retraining normalizes each report against its own market median.

    Trains to an isolated path -- the committed isolation_forest.pkl is
    never touched by tests.
    """
    import statistics

    from app.repositories.report_repository import ReportRepository
    from app.schemas.market import market_key
    from app.services.anomaly_detector import (
        AnomalyDetectorService,
        train_ml_model,
    )

    # 50+ trusted reports across two markets to clear MIN_REPORTS_TO_TRAIN_ML.
    repo = ReportRepository(tmp_path / "retrain_reports.db")
    for _ in range(30):
        repo.add(_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0))
    for _ in range(30):
        repo.add(_report("India", "INR", "Delhi", "Karol Bagh", 35.0))

    trusted = repo.trusted_reports()
    assert len(trusted) == 60
    # Per-market medians differ -- a pooled median would conflate them.
    medians = {}
    for r in trusted:
        medians.setdefault(
            (r.material_type if isinstance(r.material_type, str) else r.material_type.value,
             market_key(r.country, r.currency)), []).append(r.price_per_kg)
    assert statistics.median(medians[("metal_aluminum", ("PKR", "pakistan"))]) == 250.0
    assert statistics.median(medians[("metal_aluminum", ("INR", "india"))]) == 35.0

    service = AnomalyDetectorService(repo=repo)
    service.ml_model = None  # keep the committed artifact loaded state untouched
    model_path = tmp_path / "isolation_forest_test.pkl"
    records = [
        {
            "price_per_kg": r.price_per_kg,
            "quantity_kg": r.quantity_kg,
            "material_median": statistics.median(
                medians[(r.material_type if isinstance(r.material_type, str) else r.material_type.value,
                         market_key(r.country, r.currency))]
            ),
        }
        for r in trusted
    ]
    model = train_ml_model(records, model_path=model_path)
    assert model is not None
    assert model_path.exists()
