"""Step 8 regression tests: report trust & pending review lifecycle.

Canonical invariant:

    ACCEPTED -> eligible for price estimation + anomaly history
    PENDING  -> stored for review, NEVER market data
    REJECTED -> stored for audit, NEVER market data

Trust composes with Step 7 freshness and Steps 1-6 market/location rules:

    all reports -> accepted only -> fresh only -> market/location filtering
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.repositories.report_repository import ReportRepository
from app.schemas.report import MaterialType, PriceReport, ReportTrustStatus
from app.services.anomaly_detector import (
    anomaly_detector_service,
    comparable_prices,
    comparable_reports,
    market_median_for,
)
from app.services.price_estimator import SEED_PRICES, estimate
from app.services.report_freshness import filter_fresh_reports
from app.services.report_trust import (
    InvalidTrustTransitionError,
    accept_pending_report,
    decide_trust_status,
    filter_trusted_fresh_reports,
    filter_trusted_reports,
    get_trusted_reports,
    is_trusted_report,
    mark_accepted,
    mark_pending,
    reject_pending_report,
    review_report,
)

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
        trust_status=trust,
    )


def _days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


# ---------------------------------------------------------------------------
# §20 -- lifecycle: normal -> ACCEPTED, flagged -> PENDING
# ---------------------------------------------------------------------------

def test_canonical_trust_states_exist():
    assert {s.value for s in ReportTrustStatus} == {"pending", "accepted", "rejected"}


def test_new_normal_report_is_accepted():
    assert decide_trust_status(has_validation_reasons=False, is_anomalous=False) == ReportTrustStatus.ACCEPTED
    r = _report(trust=ReportTrustStatus.ACCEPTED)
    assert r.trust_status == "accepted"
    assert r.needs_confirmation is False
    assert is_trusted_report(r) is True


def test_flagged_report_is_pending_validation_or_anomaly():
    assert decide_trust_status(has_validation_reasons=True, is_anomalous=False) == ReportTrustStatus.PENDING
    assert decide_trust_status(has_validation_reasons=False, is_anomalous=True) == ReportTrustStatus.PENDING
    assert decide_trust_status(has_validation_reasons=True, is_anomalous=True) == ReportTrustStatus.PENDING


def test_needs_confirmation_implies_pending_no_contradiction():
    # Legacy flag alone must never stay ACCEPTED.
    r = PriceReport(
        material_type=ALU,
        quantity_kg=2.0,
        total_price=200.0,
        price_per_kg=100.0,
        currency="PKR",
        country="Pakistan",
        city="Multan",
        neighborhood="A",
        location="A",
        timestamp=NOW,
        needs_confirmation=True,
    )
    assert r.trust_status == "pending"
    assert r.needs_confirmation is True
    assert is_trusted_report(r) is False


def test_explicit_pending_sets_flag():
    r = _report(trust=ReportTrustStatus.PENDING)
    assert r.trust_status == "pending"
    assert r.needs_confirmation is True
    assert is_trusted_report(r) is False


def test_rejected_is_decided_not_pending():
    r = _report(trust=ReportTrustStatus.REJECTED)
    assert r.trust_status == "rejected"
    assert r.needs_confirmation is False
    assert is_trusted_report(r) is False


def test_mark_pending_and_accepted_preserve_market_fields():
    r = _report(price_per_kg=100.0, currency="PKR", country="Pakistan", city="Multan", neighborhood="A", timestamp=NOW)
    pending = mark_pending(r, "test flag")
    assert pending.trust_status == "pending"
    assert pending.price_per_kg == 100.0
    assert pending.currency == "PKR"
    assert pending.country == "Pakistan"
    assert pending.timestamp == NOW
    accepted = mark_accepted(pending) if False else mark_accepted(_report(trust=ReportTrustStatus.PENDING))
    # mark_accepted clears the flag and reason but keeps market data intact.
    assert accepted.trust_status == "accepted"
    assert accepted.needs_confirmation is False
    assert accepted.confirmation_reason is None


def test_pending_to_accepted():
    pending = _report(trust=ReportTrustStatus.PENDING)
    accepted = accept_pending_report(pending)
    assert accepted.trust_status == "accepted"
    assert accepted.needs_confirmation is False
    assert is_trusted_report(accepted) is True


def test_pending_to_rejected():
    pending = _report(trust=ReportTrustStatus.PENDING)
    rejected = reject_pending_report(pending, "bad data")
    assert rejected.trust_status == "rejected"
    assert rejected.needs_confirmation is False
    assert is_trusted_report(rejected) is False
    # Rejected stays stored (not deleted) -- caller keeps the object for audit.
    assert rejected.price_per_kg == pending.price_per_kg


def test_review_report_dispatcher():
    assert review_report(_report(trust=ReportTrustStatus.PENDING), "accept").trust_status == "accepted"
    assert review_report(_report(trust=ReportTrustStatus.PENDING), "reject").trust_status == "rejected"
    with pytest.raises(InvalidTrustTransitionError):
        review_report(_report(trust=ReportTrustStatus.PENDING), "maybe")


def test_invalid_transitions_rejected_deterministically():
    accepted = _report(trust=ReportTrustStatus.ACCEPTED)
    rejected = _report(trust=ReportTrustStatus.REJECTED)
    pending = _report(trust=ReportTrustStatus.PENDING)
    with pytest.raises(InvalidTrustTransitionError):
        accept_pending_report(accepted)
    with pytest.raises(InvalidTrustTransitionError):
        reject_pending_report(accepted)
    with pytest.raises(InvalidTrustTransitionError):
        accept_pending_report(rejected)
    with pytest.raises(InvalidTrustTransitionError):
        reject_pending_report(rejected)
    # REJECTED -> ACCEPTED and ACCEPTED -> REJECTED are not silent corrections.
    with pytest.raises(InvalidTrustTransitionError):
        review_report(rejected, "accept")
    with pytest.raises(InvalidTrustTransitionError):
        review_report(accepted, "reject")
    # PENDING is the only reviewable state; double-accept is invalid.
    twice = accept_pending_report(pending)
    with pytest.raises(InvalidTrustTransitionError):
        accept_pending_report(twice)


def test_pipeline_finalize_sets_trust_explicitly(monkeypatch):
    import importlib

    pipeline_mod = importlib.import_module("app.agent.workflows.pipeline")
    from app.schemas.report import AnomalyVerdict

    added: list = []
    monkeypatch.setattr(pipeline_mod.report_repo, "add", lambda r: added.append(r))
    monkeypatch.setattr(pipeline_mod, "_capture_report", lambda *a, **k: None)

    clean = _report(trust=ReportTrustStatus.ACCEPTED)
    ok_verdict = AnomalyVerdict(is_anomalous=False, reason="within range", method="deterministic")
    out = pipeline_mod._finalize(clean, ok_verdict, "ok")
    assert out["price_report"].trust_status == "accepted"
    assert len(added) == 1 and added[0].trust_status == "accepted"

    added.clear()
    flagged = _report(trust=ReportTrustStatus.ACCEPTED)
    bad_verdict = AnomalyVerdict(is_anomalous=True, reason="over double median", method="deterministic")
    out2 = pipeline_mod._finalize(flagged, bad_verdict, "flagged")
    assert out2["price_report"].trust_status == "pending"
    assert out2["price_report"].needs_confirmation is True
    # Flagged pipeline reports are held for chat review (side table), never
    # silently added to the trusted store here.
    assert added == []


# ---------------------------------------------------------------------------
# §21 -- estimator trust boundary
# ---------------------------------------------------------------------------

def _estimate_pakistan(reports, **kw):
    kw.setdefault("now", NOW)
    return estimate(
        ALU, "Income Colony", reports,
        currency="PKR", country="Pakistan", city="Multan",
        neighborhood="Income Colony", **kw,
    )


def test_estimator_ignores_pending():
    accepted = [_report(price_per_kg=100.0, timestamp=_days_ago(1)) for _ in range(5)]
    pending = [_report(price_per_kg=1000.0, timestamp=_days_ago(1), trust=ReportTrustStatus.PENDING) for _ in range(5)]
    res = _estimate_pakistan(accepted + pending)
    assert res.estimated_price_per_kg == 100.0
    assert res.tier_used == "local"
    assert res.local_report_count == 5  # pending excluded from counts
    assert res.city_report_count == 5
    assert res.country_report_count == 5


def test_estimator_ignores_rejected():
    accepted = [_report(price_per_kg=100.0, timestamp=_days_ago(1)) for _ in range(5)]
    rejected = [_report(price_per_kg=1000.0, timestamp=_days_ago(1), trust=ReportTrustStatus.REJECTED) for _ in range(5)]
    res = _estimate_pakistan(accepted + rejected)
    assert res.estimated_price_per_kg == 100.0
    assert res.local_report_count == 5


def test_estimator_only_pending_falls_back_to_seed():
    pending = [_report(price_per_kg=1000.0, timestamp=_days_ago(1), trust=ReportTrustStatus.PENDING) for _ in range(5)]
    res = _estimate_pakistan(pending)
    # Never estimate from pending data: verified seed applies.
    assert res.tier_used == "seed"
    assert res.estimated_price_per_kg == SEED_PRICES[ALU]
    assert res.local_report_count == 0


def test_estimator_only_pending_no_seed_unavailable():
    pending = [
        _report("India", "INR", "Delhi", "Karol Bagh", 1000.0, timestamp=_days_ago(1), trust=ReportTrustStatus.PENDING)
        for _ in range(5)
    ]
    res = estimate(
        ALU, "Karol Bagh", pending, currency="INR", country="India",
        city="Delhi", neighborhood="Karol Bagh", now=NOW,
    )
    assert res.tier_used == "unavailable"
    assert res.estimated_price_per_kg == 0.0
    assert res.confidence == 0.0


# ---------------------------------------------------------------------------
# §22 -- anomaly trust boundary
# ---------------------------------------------------------------------------

def test_anomaly_ignores_pending_history():
    probe = _report(price_per_kg=105.0, timestamp=NOW)
    accepted_hist = [
        _report(price_per_kg=p, timestamp=_days_ago(1))
        for p in (100.0, 110.0, 105.0)
    ]
    pending = [_report(price_per_kg=1000.0, timestamp=_days_ago(1), trust=ReportTrustStatus.PENDING) for _ in range(5)]
    prices = comparable_prices(probe, accepted_hist + pending, now=NOW)
    assert sorted(prices) == [100.0, 105.0, 110.0]
    assert market_median_for(probe, accepted_hist + pending, now=NOW) == 105.0
    # The 1000 pending value must not normalize 1000 as "normal".
    assert comparable_reports(probe, accepted_hist + pending, now=NOW) == comparable_reports(probe, accepted_hist, now=NOW)


def test_anomaly_ignores_rejected_history():
    probe = _report(price_per_kg=105.0, timestamp=NOW)
    accepted_hist = [_report(price_per_kg=p, timestamp=_days_ago(1)) for p in (100.0, 110.0, 105.0)]
    rejected = [_report(price_per_kg=1000.0, timestamp=_days_ago(1), trust=ReportTrustStatus.REJECTED) for _ in range(5)]
    assert comparable_prices(probe, accepted_hist + rejected, now=NOW) == [100.0, 110.0, 105.0]
    assert market_median_for(probe, accepted_hist + rejected, now=NOW) == 105.0


def test_tier1_thresholds_unchanged_with_trust_filter():
    history = [100.0, 100.0, 100.0]
    probe = _report(price_per_kg=100.0, timestamp=NOW)
    assert anomaly_detector_service.deterministic_check(probe, history).is_anomalous is False
    low = _report(price_per_kg=49.0, timestamp=NOW)
    assert anomaly_detector_service.deterministic_check(low, history).is_anomalous is True
    high = _report(price_per_kg=201.0, timestamp=NOW)
    assert anomaly_detector_service.deterministic_check(high, history).is_anomalous is True


def test_trusted_helpers_agree():
    mixed = [_report(trust=ReportTrustStatus.ACCEPTED), _report(trust=ReportTrustStatus.PENDING), _report(trust=ReportTrustStatus.REJECTED)]
    assert len(filter_trusted_reports(mixed)) == 1
    assert len(get_trusted_reports(mixed)) == 1
    assert all(is_trusted_report(r) for r in filter_trusted_reports(mixed))


# ---------------------------------------------------------------------------
# §23 -- trust + freshness matrix
# ---------------------------------------------------------------------------

def test_trust_freshness_matrix():
    probe = _report(timestamp=NOW)
    accepted_fresh = _report(price_per_kg=100.0, timestamp=_days_ago(1), trust=ReportTrustStatus.ACCEPTED)
    accepted_stale = _report(price_per_kg=100.0, timestamp=_days_ago(90), trust=ReportTrustStatus.ACCEPTED)
    pending_fresh = _report(price_per_kg=100.0, timestamp=_days_ago(1), trust=ReportTrustStatus.PENDING)
    pending_stale = _report(price_per_kg=100.0, timestamp=_days_ago(90), trust=ReportTrustStatus.PENDING)
    rejected_fresh = _report(price_per_kg=100.0, timestamp=_days_ago(1), trust=ReportTrustStatus.REJECTED)
    rejected_stale = _report(price_per_kg=100.0, timestamp=_days_ago(90), trust=ReportTrustStatus.REJECTED)

    usable = filter_trusted_fresh_reports(
        [accepted_fresh, accepted_stale, pending_fresh, pending_stale, rejected_fresh, rejected_stale], now=NOW
    )
    assert usable == [accepted_fresh]

    # Anomaly population agrees: only accepted+fresh is comparable.
    assert comparable_prices(probe, [accepted_fresh], now=NOW) == [100.0]
    assert comparable_prices(probe, [accepted_stale], now=NOW) == []
    assert comparable_prices(probe, [pending_fresh], now=NOW) == []
    assert comparable_prices(probe, [pending_stale], now=NOW) == []
    assert comparable_prices(probe, [rejected_fresh], now=NOW) == []
    assert comparable_prices(probe, [rejected_stale], now=NOW) == []

    # Freshness helper alone still works; trust helper composes with it.
    assert filter_fresh_reports([accepted_fresh, accepted_stale], now=NOW) == [accepted_fresh]


# ---------------------------------------------------------------------------
# §24 -- trust + market isolation
# ---------------------------------------------------------------------------

def test_trust_market_isolation():
    pak_accepted = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, timestamp=_days_ago(1)) for _ in range(5)]
    pak_pending = [
        _report("Pakistan", "PKR", "Multan", "Income Colony", 999.0, timestamp=_days_ago(1), trust=ReportTrustStatus.PENDING)
        for _ in range(5)
    ]
    ind_accepted = [
        _report("India", "INR", "Delhi", "Karol Bagh", 35.0, timestamp=_days_ago(1))
        for _ in range(5)
    ]
    ind_pending = [
        _report("India", "INR", "Delhi", "Karol Bagh", 999.0, timestamp=_days_ago(1), trust=ReportTrustStatus.PENDING)
        for _ in range(5)
    ]
    pool = pak_accepted + pak_pending + ind_accepted + ind_pending

    pkr = _estimate_pakistan(pool)
    assert pkr.estimated_price_per_kg == 250.0
    assert pkr.currency == "PKR"

    inr = estimate(
        ALU, "Karol Bagh", pool, currency="INR", country="India",
        city="Delhi", neighborhood="Karol Bagh", now=NOW,
    )
    assert inr.estimated_price_per_kg == 35.0
    assert inr.currency == "INR"

    # Anomaly populations stay isolated AND trusted.
    multan = _report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, timestamp=NOW)
    delhi = _report("India", "INR", "Delhi", "Karol Bagh", 35.0, timestamp=NOW)
    assert comparable_prices(multan, pool, now=NOW) == [250.0] * 5
    assert comparable_prices(delhi, pool, now=NOW) == [35.0] * 5


# ---------------------------------------------------------------------------
# §25 -- persistence: trust survives save -> reload
# ---------------------------------------------------------------------------

def test_trust_persistence_roundtrip(tmp_path):
    repo = ReportRepository(tmp_path / "trust_reports.db")
    reports = [
        _report(price_per_kg=100.0, trust=ReportTrustStatus.ACCEPTED),
        _report(price_per_kg=1000.0, trust=ReportTrustStatus.PENDING),
        _report(price_per_kg=2000.0, trust=ReportTrustStatus.REJECTED),
    ]
    for r in reports:
        repo.add(r)
    loaded = repo.all_reports()
    assert len(loaded) == 3
    by_price = {r.price_per_kg: r for r in loaded}
    assert by_price[100.0].trust_status == "accepted"
    assert by_price[1000.0].trust_status == "pending"
    assert by_price[2000.0].trust_status == "rejected"
    # Canonical filter: only accepted is market data.
    assert [r.price_per_kg for r in repo.trusted_reports()] == [100.0]
    assert [r.price_per_kg for r in repo.get_trusted_reports()] == [100.0]


# ---------------------------------------------------------------------------
# §26 -- legacy reports without trust state
# ---------------------------------------------------------------------------

def test_legacy_main_table_rows_default_accepted():
    # Pre-Step-8 main-table rows had no trust_status and needs_confirmation=False.
    # The table only ever stored validated reports, so ACCEPTED preserves behavior.
    old_json = json.dumps({
        "material_type": "plastic_pet",
        "quantity_kg": 5.0,
        "price_paid_pkr": 700.0,
        "price_paid_pkr_per_kg": 140.0,
        "location": "Gulgasht",
        "needs_confirmation": False,
    })
    parsed = PriceReport.model_validate_json(old_json)
    assert parsed.trust_status == "accepted"
    assert is_trusted_report(parsed) is True


def test_legacy_pending_rows_become_pending_not_accepted():
    # Legacy pending_reports rows had needs_confirmation=True and no trust_status.
    # They must NOT be silently declared accepted.
    old_json = json.dumps({
        "material_type": "metal_aluminum",
        "quantity_kg": 2.0,
        "total_price": 200.0,
        "price_per_kg": 100.0,
        "currency": "PKR",
        "country": "Pakistan",
        "city": "Multan",
        "neighborhood": "A",
        "location": "A",
        "timestamp": NOW.isoformat(),
        "needs_confirmation": True,
        "confirmation_reason": "needs review",
    })
    parsed = PriceReport.model_validate_json(old_json)
    assert parsed.trust_status == "pending"
    assert is_trusted_report(parsed) is False
