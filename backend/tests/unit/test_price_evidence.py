"""Step 9 regression tests: price estimate evidence & confidence integrity.

Every estimate must explain itself (source/scope/report_count/market/
freshness/seed_source) from the SAME eligible population the estimator
prices from::

    ACCEPTED + FRESH + same material + same market + appropriate scope

PENDING, REJECTED, stale, and foreign-market reports never contribute to
value, confidence, evidence counts, or sample counts. Confidence math is
preserved exactly; seed/unavailable never inherit report confidence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.schemas.market import market_key
from app.schemas.report import MaterialType, PriceReport, ReportTrustStatus
from app.services.price_estimator import SEED_PRICES, estimate

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


def _estimate_pakistan(reports, **kw):
    kw.setdefault("now", NOW)
    return estimate(
        ALU, "Income Colony", reports,
        currency="PKR", country="Pakistan", city="Multan",
        neighborhood="Income Colony", **kw,
    )


# ---------------------------------------------------------------------------
# A. Accepted + fresh report contributes
# ---------------------------------------------------------------------------

def test_a_accepted_fresh_contributes_with_reports_evidence():
    reports = [_report(price_per_kg=250.0, timestamp=_days_ago(1)) for _ in range(5)]
    res = _estimate_pakistan(reports)
    assert res.tier_used == "local"
    assert res.estimated_price_per_kg == 250.0
    # Preserved local confidence: min(0.90, 0.55 + 0.35*(5/15)) == 0.667.
    assert res.confidence == round(min(0.90, 0.55 + 0.35 * (5 / 15)), 3) == 0.667
    assert res.local_report_count == 5
    assert res.city_report_count == 5
    assert res.country_report_count == 5
    ev = res.evidence
    assert ev is not None
    assert ev.source == "reports"
    assert ev.scope == "neighborhood"
    assert ev.report_count == 5
    assert ev.report_count == res.local_report_count
    assert ev.currency == "PKR"
    assert ev.country == "Pakistan"
    assert ev.market_key() == market_key("Pakistan", "PKR")
    assert ev.freshness_days == settings.REPORT_FRESHNESS_DAYS
    assert ev.seed_source is None


# ---------------------------------------------------------------------------
# B. Pending reports never contribute
# ---------------------------------------------------------------------------

def test_b_pending_does_not_contribute():
    accepted = [_report(price_per_kg=100.0, timestamp=_days_ago(1)) for _ in range(5)]
    baseline = _estimate_pakistan(accepted)
    pending = [
        _report(price_per_kg=1000.0, timestamp=_days_ago(1), trust=ReportTrustStatus.PENDING)
        for _ in range(5)
    ]
    res = _estimate_pakistan(accepted + pending)
    assert res.estimated_price_per_kg == baseline.estimated_price_per_kg == 100.0
    assert res.confidence == baseline.confidence
    assert res.local_report_count == 5
    assert res.city_report_count == 5
    assert res.country_report_count == 5
    assert res.evidence is not None
    assert res.evidence.source == "reports"
    assert res.evidence.report_count == 5


def test_b_only_pending_falls_back_to_seed_evidence():
    pending = [
        _report(price_per_kg=1000.0, timestamp=_days_ago(1), trust=ReportTrustStatus.PENDING)
        for _ in range(5)
    ]
    res = _estimate_pakistan(pending)
    assert res.tier_used == "seed"
    assert res.estimated_price_per_kg == SEED_PRICES[ALU]
    assert res.local_report_count == 0
    assert res.city_report_count == 0
    assert res.country_report_count == 0
    assert res.evidence is not None
    assert res.evidence.source == "seed"
    assert res.evidence.scope == "seed"
    assert res.evidence.report_count == 0


# ---------------------------------------------------------------------------
# C. Rejected reports never contribute
# ---------------------------------------------------------------------------

def test_c_rejected_does_not_contribute():
    accepted = [_report(price_per_kg=100.0, timestamp=_days_ago(1)) for _ in range(5)]
    baseline = _estimate_pakistan(accepted)
    rejected = [
        _report(price_per_kg=1000.0, timestamp=_days_ago(1), trust=ReportTrustStatus.REJECTED)
        for _ in range(5)
    ]
    res = _estimate_pakistan(accepted + rejected)
    assert res.estimated_price_per_kg == baseline.estimated_price_per_kg == 100.0
    assert res.confidence == baseline.confidence
    assert res.local_report_count == 5
    assert res.evidence is not None
    assert res.evidence.source == "reports"
    assert res.evidence.report_count == 5


# ---------------------------------------------------------------------------
# D. Stale accepted reports never contribute
# ---------------------------------------------------------------------------

def test_d_stale_accepted_does_not_contribute():
    stale = [_report(price_per_kg=1000.0, timestamp=_days_ago(90)) for _ in range(5)]
    res = _estimate_pakistan(stale)
    assert res.tier_used == "seed"
    assert res.estimated_price_per_kg == SEED_PRICES[ALU]
    assert res.confidence == 0.20
    assert res.local_report_count == 0
    assert res.evidence is not None
    assert res.evidence.source == "seed"
    assert res.evidence.scope == "seed"
    assert res.evidence.report_count == 0
    assert res.evidence.seed_source == settings.SEED_SOURCE


def test_d_fresh_beats_stale_evidence_counts_fresh_only():
    fresh = [_report(price_per_kg=100.0, timestamp=_days_ago(1)) for _ in range(5)]
    stale = [_report(price_per_kg=1000.0, timestamp=_days_ago(120)) for _ in range(5)]
    res = _estimate_pakistan(fresh + stale)
    assert res.estimated_price_per_kg == 100.0
    assert res.tier_used == "local"
    assert res.local_report_count == 5
    assert res.evidence is not None
    assert res.evidence.source == "reports"
    assert res.evidence.report_count == 5


# ---------------------------------------------------------------------------
# E. Market isolation (Pakistan/PKR, India/INR, USA/USD)
# ---------------------------------------------------------------------------

def test_e_markets_do_not_share_evidence():
    pool = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, _days_ago(1)) for _ in range(5)]
    pool += [_report("India", "INR", "Delhi", "Karol Bagh", 35.0, _days_ago(1)) for _ in range(5)]
    pool += [_report("United States", "USD", "Chicago", "Pilsen", 1.0, _days_ago(1)) for _ in range(5)]

    pkr = _estimate_pakistan(pool)
    inr = estimate(
        ALU, "Karol Bagh", pool, currency="INR", country="India",
        city="Delhi", neighborhood="Karol Bagh", now=NOW,
    )
    usd = estimate(
        ALU, "Pilsen", pool, currency="USD", country="United States",
        city="Chicago", neighborhood="Pilsen", now=NOW,
    )
    assert pkr.estimated_price_per_kg == 250.0
    assert inr.estimated_price_per_kg == 35.0
    assert usd.estimated_price_per_kg == 1.0
    assert pkr.evidence is not None and inr.evidence is not None and usd.evidence is not None
    assert pkr.evidence.market_key() == ("PKR", "pakistan")
    assert inr.evidence.market_key() == ("INR", "india")
    assert usd.evidence.market_key() == ("USD", "united states")
    assert pkr.evidence.market_key() != inr.evidence.market_key() != usd.evidence.market_key()
    assert pkr.evidence.report_count == 5
    assert inr.evidence.report_count == 5
    assert usd.evidence.report_count == 5
    # Same nominal 500 in different currencies must never pool.
    same_price = [_report("Pakistan", "PKR", "Multan", "Income Colony", 500.0, _days_ago(1)) for _ in range(5)]
    same_price += [_report("India", "INR", "Delhi", "Karol Bagh", 500.0, _days_ago(1)) for _ in range(5)]
    pkr2 = _estimate_pakistan(same_price)
    inr2 = estimate(
        ALU, "Karol Bagh", same_price, currency="INR", country="India",
        city="Delhi", neighborhood="Karol Bagh", now=NOW,
    )
    assert pkr2.evidence.market_key() != inr2.evidence.market_key()
    assert pkr2.local_report_count == 5
    assert inr2.local_report_count == 5


def test_e_foreign_pending_cannot_pollute_evidence():
    pak_accepted = [_report("Pakistan", "PKR", "Multan", "Income Colony", 250.0, _days_ago(1)) for _ in range(5)]
    ind_pending = [
        _report("India", "INR", "Delhi", "Karol Bagh", 999.0, _days_ago(1), trust=ReportTrustStatus.PENDING)
        for _ in range(5)
    ]
    res = _estimate_pakistan(pak_accepted + ind_pending)
    assert res.estimated_price_per_kg == 250.0
    assert res.evidence is not None
    assert res.evidence.market_key() == ("PKR", "pakistan")
    assert res.evidence.report_count == 5


# ---------------------------------------------------------------------------
# F. Geographic scope fallthrough
# ---------------------------------------------------------------------------

def test_f_neighborhood_scope():
    reports = [_report(price_per_kg=250.0, timestamp=_days_ago(1)) for _ in range(5)]
    res = _estimate_pakistan(reports)
    assert res.tier_used == "local"
    assert res.evidence is not None
    assert res.evidence.source == "reports"
    assert res.evidence.scope == "neighborhood"
    assert res.evidence.report_count == 5 == res.local_report_count


def test_f_blended_neighborhood_city_scope():
    # 5 in the requested neighborhood + 5 elsewhere in Multan => city pool 10.
    local = [_report(price_per_kg=250.0, timestamp=_days_ago(1)) for _ in range(5)]
    other = [
        _report(country="Pakistan", currency="PKR", city="Multan", neighborhood="Samejabad",
                price_per_kg=260.0, timestamp=_days_ago(1), location="Samejabad")
        for _ in range(5)
    ]
    res = _estimate_pakistan(local + other)
    assert res.tier_used == "local+city"
    assert res.evidence is not None
    assert res.evidence.source == "reports"
    # Blended tier must not pretend purely local or purely city.
    assert res.evidence.scope == "neighborhood+city"
    # Pools are nested: distinct supporting reports are the city pool.
    assert res.local_report_count == 5
    assert res.city_report_count == 10
    assert res.evidence.report_count == 10 == res.city_report_count
    # Preserved blended confidence: min(0.95, 0.6 + 0.35*(5/10)).
    assert res.confidence == round(min(0.95, 0.6 + 0.35 * (5 / 10)), 3) == 0.775


def test_f_city_scope():
    stale_local = [_report(price_per_kg=1000.0, timestamp=_days_ago(90)) for _ in range(5)]
    fresh_city = [
        _report(country="Pakistan", currency="PKR", city="Multan", neighborhood="Samejabad",
                price_per_kg=100.0, timestamp=_days_ago(2), location="Samejabad")
        for _ in range(10)
    ]
    res = _estimate_pakistan(stale_local + fresh_city)
    assert res.tier_used == "city"
    assert res.local_report_count == 0
    assert res.city_report_count == 10
    assert res.evidence is not None
    assert res.evidence.source == "reports"
    assert res.evidence.scope == "city"
    assert res.evidence.report_count == 10 == res.city_report_count
    # Preserved city confidence: min(0.70, 0.35 + 0.35*(10/20)).
    assert res.confidence == round(min(0.70, 0.35 + 0.35 * (10 / 20)), 3) == 0.525


def test_f_country_scope():
    reports = [_report("Pakistan", "PKR", "Multan", f"Multan Area {i}", 250.0, _days_ago(1)) for i in range(5)]
    reports += [_report("Pakistan", "PKR", "Lahore", f"Lahore Area {i}", 250.0, _days_ago(1)) for i in range(5)]
    res = estimate(
        ALU, "Somewhere New", reports, currency="PKR", country="Pakistan",
        city="Karachi", neighborhood="Somewhere New", now=NOW,
    )
    assert res.tier_used == "country"
    assert res.city_report_count == 0
    assert res.local_report_count == 0
    assert res.country_report_count == 10
    assert res.evidence is not None
    assert res.evidence.source == "reports"
    assert res.evidence.scope == "country"
    assert res.evidence.report_count == 10 == res.country_report_count


def test_f_seed_scope():
    res = _estimate_pakistan([])
    assert res.tier_used == "seed"
    assert res.evidence is not None
    assert res.evidence.source == "seed"
    assert res.evidence.scope == "seed"
    assert res.evidence.report_count == 0


def test_f_unavailable_scope():
    res = estimate(
        ALU, "Le Marais", [], currency="EUR", country="France",
        city="Paris", neighborhood="Le Marais", now=NOW,
    )
    assert res.tier_used == "unavailable"
    assert res.evidence is not None
    assert res.evidence.source == "unavailable"
    assert res.evidence.scope == "unavailable"
    assert res.evidence.report_count == 0


# ---------------------------------------------------------------------------
# G. Seed fallback integrity
# ---------------------------------------------------------------------------

def test_g_seed_evidence_has_no_fake_reports():
    res = _estimate_pakistan([])
    assert res.tier_used == "seed"
    assert res.estimated_price_per_kg == SEED_PRICES[ALU] == 1050.0
    assert res.confidence == 0.20
    assert res.local_report_count == 0
    assert res.city_report_count == 0
    assert res.country_report_count == 0
    ev = res.evidence
    assert ev is not None
    assert ev.source == "seed"
    assert ev.scope == "seed"
    assert ev.report_count == 0
    assert ev.seed_source == settings.SEED_SOURCE
    assert ev.market_key() == ("PKR", "pakistan")
    assert ev.freshness_days == settings.REPORT_FRESHNESS_DAYS


def test_g_only_verified_market_seed_used():
    from app.services.price_estimator import _seed_for, seed_info_for

    assert _seed_for(ALU, "Pakistan", "PKR") == 1050.0
    assert _seed_for(ALU, "India", "INR") is None
    assert _seed_for(ALU, "United States", "USD") is None
    info = seed_info_for(ALU, "Pakistan", "PKR")
    assert info is not None and info["source"] == settings.SEED_SOURCE
    res = _estimate_pakistan([])
    assert res.evidence is not None
    assert res.evidence.seed_source == info["source"]


# ---------------------------------------------------------------------------
# H. Unavailable markets never get a seed
# ---------------------------------------------------------------------------

def test_h_unavailable_evidence_no_seed_leakage():
    for country, currency, city, neighborhood in [
        ("India", "INR", "Delhi", "Karol Bagh"),
        ("United States", "USD", "Chicago", "Pilsen"),
        ("France", "EUR", "Paris", "Le Marais"),
    ]:
        res = estimate(
            ALU, neighborhood, [], currency=currency, country=country,
            city=city, neighborhood=neighborhood, now=NOW,
        )
        assert res.tier_used == "unavailable", (country, currency)
        assert res.estimated_price_per_kg == 0.0
        assert res.confidence == 0.0
        assert res.local_report_count == 0
        assert res.city_report_count == 0
        assert res.country_report_count == 0
        ev = res.evidence
        assert ev is not None
        assert ev.source == "unavailable"
        assert ev.scope == "unavailable"
        assert ev.report_count == 0
        assert ev.seed_source is None
        assert ev.market_key() == market_key(country, currency)
        assert res.estimated_price_per_kg != SEED_PRICES[ALU]


def test_h_stale_only_no_seed_is_unavailable():
    stale = [_report("India", "INR", "Delhi", "Karol Bagh", 999.0, _days_ago(200)) for _ in range(10)]
    res = estimate(
        ALU, "Karol Bagh", stale, currency="INR", country="India",
        city="Delhi", neighborhood="Karol Bagh", now=NOW,
    )
    assert res.tier_used == "unavailable"
    assert res.confidence == 0.0
    assert res.evidence is not None
    assert res.evidence.source == "unavailable"
    assert res.evidence.report_count == 0


# ---------------------------------------------------------------------------
# I. Currency normalization maps to the same canonical market
# ---------------------------------------------------------------------------

def test_i_currency_normalization_same_market():
    lower = estimate(
        ALU, "Income Colony", [], currency="pkr", country="Pakistan",
        city="Multan", neighborhood="Income Colony", now=NOW,
    )
    upper = estimate(
        ALU, "Income Colony", [], currency="PKR", country="Pakistan",
        city="Multan", neighborhood="Income Colony", now=NOW,
    )
    assert lower.currency == upper.currency == "PKR"
    assert lower.tier_used == upper.tier_used == "seed"
    assert lower.estimated_price_per_kg == upper.estimated_price_per_kg
    assert lower.evidence is not None and upper.evidence is not None
    assert lower.evidence.market_key() == upper.evidence.market_key() == ("PKR", "pakistan")
    assert market_key("Pakistan", "pkr") == ("PKR", "pakistan")


def test_i_mismatched_market_stays_distinct():
    # India/PKR is its own market -- never the verified Pakistan/PKR seed.
    res = estimate(
        ALU, "Karol Bagh", [], currency="PKR", country="India",
        city="Delhi", neighborhood="Karol Bagh", now=NOW,
    )
    assert res.currency == "PKR"
    assert res.tier_used == "unavailable"
    assert res.evidence is not None
    assert res.evidence.market_key() == ("PKR", "india")
    assert res.evidence.market_key() != ("PKR", "pakistan")


# ---------------------------------------------------------------------------
# J. Evidence/count consistency for every tier
# ---------------------------------------------------------------------------

def test_j_evidence_agrees_with_eligible_population():
    # Neighborhood tier.
    reports = [_report(price_per_kg=250.0, timestamp=_days_ago(1)) for _ in range(5)]
    res = _estimate_pakistan(reports)
    assert res.evidence is not None
    assert res.evidence.report_count == res.local_report_count == 5

    # Blended tier: distinct city pool.
    blended = [_report(price_per_kg=250.0, timestamp=_days_ago(1)) for _ in range(5)]
    blended += [
        _report(country="Pakistan", currency="PKR", city="Multan", neighborhood="Samejabad",
                price_per_kg=260.0, timestamp=_days_ago(1), location="Samejabad")
        for _ in range(5)
    ]
    bres = _estimate_pakistan(blended)
    assert bres.tier_used == "local+city"
    assert bres.evidence is not None
    assert bres.evidence.report_count == bres.city_report_count == 10
    assert bres.evidence.report_count != bres.local_report_count + bres.city_report_count  # no double-count

    # City tier.
    stale_local = [_report(price_per_kg=1000.0, timestamp=_days_ago(90)) for _ in range(5)]
    fresh_city = [
        _report(country="Pakistan", currency="PKR", city="Multan", neighborhood="Samejabad",
                price_per_kg=100.0, timestamp=_days_ago(2), location="Samejabad")
        for _ in range(10)
    ]
    cres = _estimate_pakistan(stale_local + fresh_city)
    assert cres.tier_used == "city"
    assert cres.evidence is not None
    assert cres.evidence.report_count == cres.city_report_count == 10

    # Country tier.
    market = [_report("Pakistan", "PKR", "Multan", f"M {i}", 250.0, _days_ago(1)) for i in range(5)]
    market += [_report("Pakistan", "PKR", "Lahore", f"L {i}", 250.0, _days_ago(1)) for i in range(5)]
    country_res = estimate(
        ALU, "Somewhere New", market, currency="PKR", country="Pakistan",
        city="Karachi", neighborhood="Somewhere New", now=NOW,
    )
    assert country_res.tier_used == "country"
    assert country_res.evidence is not None
    assert country_res.evidence.report_count == country_res.country_report_count == 10

    # Seed and unavailable always zero.
    seed_res = _estimate_pakistan([])
    assert seed_res.evidence is not None
    assert seed_res.evidence.report_count == 0
    assert seed_res.local_report_count == seed_res.city_report_count == seed_res.country_report_count == 0
    unav = estimate(ALU, "Le Marais", [], currency="EUR", country="France",
                    city="Paris", neighborhood="Le Marais", now=NOW)
    assert unav.evidence is not None
    assert unav.evidence.report_count == 0


def test_j_evidence_window_matches_applied_freshness():
    reports = [_report(price_per_kg=250.0, timestamp=_days_ago(1)) for _ in range(5)]
    default = _estimate_pakistan(reports)
    assert default.evidence is not None
    assert default.evidence.freshness_days == settings.REPORT_FRESHNESS_DAYS
    custom = _estimate_pakistan(reports, freshness_days=7)
    assert custom.evidence is not None
    assert custom.evidence.freshness_days == 7
    # A 10-day-old report is fresh under the default window but stale under 7d.
    aging = [_report(price_per_kg=250.0, timestamp=_days_ago(10)) for _ in range(5)]
    fresh_default = _estimate_pakistan(aging)
    assert fresh_default.tier_used == "local"
    assert fresh_default.evidence is not None
    assert fresh_default.evidence.report_count == 5
    stale_custom = _estimate_pakistan(aging, freshness_days=7)
    assert stale_custom.tier_used == "seed"
    assert stale_custom.evidence is not None
    assert stale_custom.evidence.source == "seed"
    assert stale_custom.evidence.report_count == 0


def test_j_thin_data_tier_evidence():
    # Below-threshold data still reports source=reports with the thin pool.
    thin = [_report(price_per_kg=100.0, timestamp=_days_ago(1)) for _ in range(2)]
    res = _estimate_pakistan(thin)
    assert res.tier_used == "local"
    assert res.evidence is not None
    assert res.evidence.source == "reports"
    assert res.evidence.scope == "neighborhood"
    assert res.evidence.report_count == 2
    # Preserved thin-data confidence: 0.20 + 0.15*(2/5).
    assert res.confidence == round(0.20 + 0.15 * (2 / 5), 3)
