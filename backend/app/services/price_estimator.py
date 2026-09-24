"""
Price Estimator service for Scrapwisest.

Market- and location-scoped 4-tier fallback pricing chain::

    Tier 1 (neighborhood) -- median of recent reports for this material in
        the same market (country + currency) AND the same city AND the same
        neighborhood. Reported as ``tier_used="local"`` for backwards
        compatibility (local == neighborhood scope).
    Tier 2 (city)         -- median across neighborhoods in the same city,
        same country, same currency. Reported as ``tier_used="city"``.
    Tier 3 (country)      -- median across the same market
        (same material, country, and currency). Reported as
        ``tier_used="country"``.
    Tier 4 (seed)         -- verified per-market baseline price, or a safe
        no-estimate signal when the market has no verified seed.

A report from Multan, Pakistan (PKR) never contributes to an estimate for
Delhi, India (INR) or Chicago, USA (USD). There is deliberately NO currency
conversion here: the estimator quotes the local market price in the
requested market's currency.
"""

from __future__ import annotations

import logging
import statistics
from typing import List, Optional, Union

from app.core.config import settings
from app.repositories.report_repository import ReportRepository, report_repo
from app.schemas.market import UNKNOWN_CURRENCY, market_key
from app.schemas.price import PriceEstimate
from app.schemas.report import MaterialType, PriceReport
from app.services.location_resolver import (
    neighborhood_label,
    normalize_currency,
    normalize_location,
    normalize_place_part,
    same_city,
)

logger = logging.getLogger(__name__)

# Step 6: verified seed prices, keyed by (material, market) where market
# is the canonical (currency, country) pair from ``market_key()`` -- the
# SAME helper used by reports, the anomaly detector, and picker context.
# There is exactly one market-key implementation; no "Pakistan/PKR",
# "pk", or "pakistan_pkr" duplicates exist.
#
# Only the Pakistan/PKR market has verified seeds; every other market maps
# to no entry, which the estimator treats as "no market seed" instead of
# reusing or inventing numbers. Never convert PKR seeds to INR/USD, never
# apply exchange rates, never guess international values.
_VERIFIED_SEED_MARKET: tuple[str, str] = market_key(
    settings.SEED_MARKET_COUNTRY, settings.SEED_MARKET_CURRENCY
)
_SEED_BY_MARKET: dict[tuple[str, str, str], float] = {}
for _mat_value, _seed in settings.SEED_PRICES.items():
    _mat_norm = _mat_value.strip().lower()
    _SEED_BY_MARKET[(_mat_norm, _VERIFIED_SEED_MARKET[0], _VERIFIED_SEED_MARKET[1])] = _seed

# Verified price bands, keyed the same way: (material, market). Only the
# Pakistan/PKR market has verified bands. Other markets have no entry --
# validators must skip the band check for them instead of judging e.g. a
# USD price against a PKR-denominated range. Never convert bands.
_BAND_BY_MARKET: dict[tuple[str, str, str], tuple[float, float]] = {}
for _band_mat, _band in settings.PRICE_PER_KG_BANDS.items():
    _BAND_BY_MARKET[
        (_band_mat.strip().lower(), _VERIFIED_SEED_MARKET[0], _VERIFIED_SEED_MARKET[1])
    ] = (float(_band[0]), float(_band[1]))

# Backwards-compatible material-only view of the verified Pakistan/PKR
# seeds. DEPRECATED for market-aware code: it is NOT a global table and
# must never be indexed as ``SEED_PRICES[material]`` for an arbitrary
# market. New code must use ``_seed_for(material, country, currency)``
# (or ``settings.seed_price_for``) instead. Kept only so legacy
# Pakistan/PKR callers and existing tests keep working with identical
# values.
SEED_PRICES: dict[MaterialType, float] = {
    MaterialType.PLASTIC_PET: settings.SEED_PRICES["plastic_pet"],
    MaterialType.PLASTIC_HDPE: settings.SEED_PRICES["plastic_hdpe"],
    MaterialType.GLASS: settings.SEED_PRICES["glass"],
    MaterialType.METAL_ALUMINUM: settings.SEED_PRICES["metal_aluminum"],
    MaterialType.METAL_STEEL: settings.SEED_PRICES["metal_steel"],
    MaterialType.CARDBOARD: settings.SEED_PRICES["cardboard"],
    MaterialType.MIXED_PAPER: settings.SEED_PRICES["mixed_paper"],
    MaterialType.OTHER: settings.SEED_PRICES["other"],
}

# Legacy unknown market (requests/reports that never named a currency or
# country) falls back to the verified Pakistan/PKR seeds so pre-global
# callers keep working. This is a documented compatibility exception, not
# a guess: historically every legacy row came from that market.
#
# It applies ONLY when the request names NO market context at all, i.e.
# ``market_key(country, currency) == ("unknown", "")``. An explicit foreign
# market (India/INR, USA/USD, France/EUR, or a mismatched India/PKR) NEVER
# receives this fallback -- a missing market stays missing (seed -> None,
# estimator tier -> "unavailable").
_LEGACY_SEED_MARKET: tuple[str, str] = (UNKNOWN_CURRENCY, "")


def _material_value(material: MaterialType | str) -> str:
    raw = material.value if hasattr(material, "value") else str(material)
    return raw.strip().lower()


def _seed_for(
    material: MaterialType | str, country: str | None, currency: str | None
) -> Optional[float]:
    """Verified seed for ``(material, market)``, or None when unknown.

    Exact-match lookup only::

        material + requested market -> seed if that market has one, else None.

    Only the Pakistan/PKR market (and the legacy unknown market, for
    backwards compatibility -- see ``_LEGACY_SEED_MARKET``) has verified
    seeds. All other markets return None so the estimator never fabricates
    pricing data and never reuses a PKR seed as an INR/USD seed.

    Never invents values, never converts currencies, never reuses another
    country's seed as if it belonged to the requested market.
    """
    mat = _material_value(material)
    cur, ctry = market_key(country, currency)
    if (cur, ctry) == _LEGACY_SEED_MARKET:
        verified_cur, verified_ctry = _VERIFIED_SEED_MARKET
        return _SEED_BY_MARKET.get((mat, verified_cur, verified_ctry))
    return _SEED_BY_MARKET.get((mat, cur, ctry))


def _band_for(
    material: MaterialType | str, country: str | None, currency: str | None
) -> Optional[tuple[float, float]]:
    """Verified sanity band for ``(material, market)``, or None.

    Same market identity as seeds: only Pakistan/PKR (plus the legacy
    unknown market for backwards compatibility) has bands. Explicit foreign
    markets return None so validators skip the check instead of judging a
    foreign-currency price against a PKR-denominated range. Never convert.
    """
    mat = _material_value(material)
    cur, ctry = market_key(country, currency)
    if (cur, ctry) == _LEGACY_SEED_MARKET:
        verified_cur, verified_ctry = _VERIFIED_SEED_MARKET
        return _BAND_BY_MARKET.get((mat, verified_cur, verified_ctry))
    return _BAND_BY_MARKET.get((mat, cur, ctry))


def seed_info_for(
    material: MaterialType | str, country: str | None, currency: str | None
) -> Optional[dict]:
    """Minimal seed provenance for ``(material, market)`` (no management UI).

    Returns ``{"material", "country", "currency", "price_per_kg", "source"}``
    for verified markets, else None. The legacy unknown market resolves to
    the Pakistan/PKR provenance for backwards compatibility.
    """
    price = _seed_for(material, country, currency)
    if price is None:
        return None
    cur, ctry = market_key(country, currency)
    if (cur, ctry) == _LEGACY_SEED_MARKET:
        return {
            "material": _material_value(material),
            "country": settings.SEED_MARKET_COUNTRY,
            "currency": settings.SEED_MARKET_CURRENCY,
            "price_per_kg": price,
            "source": settings.SEED_SOURCE,
        }
    return {
        "material": _material_value(material),
        "country": settings.SEED_MARKET_COUNTRY,
        "currency": settings.SEED_MARKET_CURRENCY,
        "price_per_kg": price,
        "source": settings.SEED_SOURCE,
    }


def _report_matches_market(
    report: PriceReport,
    material_val: str,
    request_currency: str,
    request_country: Optional[str],
) -> bool:
    """True when a report belongs to the requested market scope.

    Currency must always match exactly (never mix PKR/INR/USD). Country
    must match exactly when the request names one; a request that names no
    country is treated as a legacy wildcard for that dimension only, so old
    callers that pass just a location string keep working while never
    mixing currencies.
    """
    if _material_value(report.material_type) != material_val:
        return False
    if report.needs_confirmation:
        return False
    if normalize_currency(report.currency) != request_currency:
        return False
    if request_country is None:
        return True
    report_country = normalize_place_part(report.country)
    return (report_country or "").lower() == request_country.lower()


class PriceEstimatorService:
    def __init__(self, repo: Optional[ReportRepository] = None):
        self.repo = repo or report_repo
        self.min_local = settings.MIN_LOCAL_REPORTS
        self.min_city = settings.MIN_CITY_REPORTS
        self.seed_prices = SEED_PRICES

    def estimate(
        self,
        material: MaterialType,
        location: str,
        reports: Optional[List[PriceReport]] = None,
        currency: str = UNKNOWN_CURRENCY,
        country: Optional[str] = None,
        city: Optional[str] = None,
        neighborhood: Optional[str] = None,
    ) -> PriceEstimate:
        """
        Market- and location-scoped scrap price estimate.

        Pools only reports for the same material in the same market (same
        currency, and same country when the request names one), then falls
        back neighborhood -> city -> country/market -> market-specific seed.
        Use the requested market's local currency; never convert currencies.
        """
        if reports is None:
            reports = self.repo.trusted_reports()

        material_val = _material_value(material)
        request_currency = normalize_currency(currency)
        request_country_part = normalize_place_part(country)
        request_country = request_country_part.lower() if request_country_part else None
        request_city_part = normalize_place_part(city)
        request_city = request_city_part.lower() if request_city_part else None

        raw_place = (
            (neighborhood or "").strip()
            or (location or "").strip()
            or (city or "").strip()
            or "unknown"
        )
        display_location = normalize_location(raw_place)

        # City-only requests (e.g. location == city, no neighborhood) skip
        # the neighborhood tier and go straight to city scope.
        city_only = False
        if not (neighborhood or "").strip() and request_city_part and (location or "").strip():
            loc_norm = normalize_location(location).lower()
            if loc_norm == request_city_part.lower() or (
                location or ""
            ).strip().lower() == request_city_part.lower():
                city_only = True

        request_label: Optional[str] = None
        if not city_only:
            request_label = neighborhood_label(neighborhood, location)

        logger.info(
            "Calculating market-scoped price estimate for material='%s' "
            "market=(currency='%s', country='%s', city='%s', neighborhood='%s')",
            material_val,
            request_currency,
            request_country_part,
            request_city_part,
            neighborhood,
        )

        # Tier 0: market pool -- same material, same currency, same country
        # (country wildcard only when the request names none, for legacy
        # callers). Nothing outside this pool may influence the estimate.
        market_reports = [
            r
            for r in reports
            if _report_matches_market(r, material_val, request_currency, request_country)
        ]

        # Tier 2 pool: same city within the market. A request without a city
        # keeps the legacy wildcard so old location-only callers still work;
        # explicit cities must match on both city AND country (never compare
        # city names alone).
        if request_city is None:
            city_reports = list(market_reports)
        else:
            city_reports = [
                r
                for r in market_reports
                if same_city(request_city_part, request_country_part, r.city, r.country)
            ]

        # Tier 1 pool: same neighborhood within the same city/market, so an
        # "Income Colony" in one city/country can never match another.
        if request_label is None:
            neighborhood_reports: List[PriceReport] = []
        else:
            wanted = request_label.lower()
            neighborhood_reports = [
                r
                for r in city_reports
                if (
                    neighborhood_label(r.neighborhood, r.location) or ""
                ).lower()
                == wanted
            ]

        country_reports = list(market_reports)

        local_prices = [r.price_per_kg for r in neighborhood_reports]
        city_prices = [r.price_per_kg for r in city_reports]
        country_prices = [r.price_per_kg for r in country_reports]
        seed = _seed_for(material, request_country_part, request_currency)

        n_local = len(local_prices)
        n_city = len(city_prices)
        n_country = len(country_prices)

        if n_local >= self.min_local and n_city >= self.min_city:
            local_w = n_local / (n_local + n_city)
            city_w = 1.0 - local_w
            price = local_w * statistics.median(local_prices) + city_w * statistics.median(city_prices)
            conf = min(0.95, 0.6 + 0.35 * (n_local / (self.min_local * 2)))
            tier = "local+city"

        elif n_local >= self.min_local:
            price = statistics.median(local_prices)
            conf = min(0.90, 0.55 + 0.35 * (n_local / (self.min_local * 3)))
            tier = "local"

        elif n_city >= self.min_city:
            city_med = statistics.median(city_prices)
            if seed is not None:
                city_w = min(0.85, n_city / (self.min_city * 2))
                price = city_w * city_med + (1.0 - city_w) * seed
            else:
                price = city_med
            conf = min(0.70, 0.35 + 0.35 * (n_city / (self.min_city * 2)))
            tier = "city"

        elif n_country >= self.min_city:
            country_med = statistics.median(country_prices)
            if seed is not None:
                country_w = min(0.85, n_country / (self.min_city * 2))
                price = country_w * country_med + (1.0 - country_w) * seed
            else:
                price = country_med
            conf = min(0.70, 0.35 + 0.35 * (n_country / (self.min_city * 2)))
            tier = "country"

        elif n_local > 0 or n_city > 0 or n_country > 0:
            if local_prices:
                prices = local_prices
                threshold = self.min_local
                tier = "local"
            elif city_prices:
                prices = city_prices
                threshold = self.min_city
                tier = "city"
            else:
                prices = country_prices
                threshold = self.min_city
                tier = "country"
            data_med = statistics.median(prices)
            n = len(prices)
            data_w = n / threshold
            if seed is not None:
                price = data_w * data_med + (1.0 - data_w) * seed
            else:
                price = data_med
            conf = 0.20 + 0.15 * data_w

        else:
            if seed is not None:
                price = seed
                conf = 0.20
                tier = "seed"
            else:
                # No reports and no verified seed for this market: signal
                # "no estimate" instead of inventing a number.
                res = PriceEstimate(
                    material_type=material,
                    location=display_location,
                    estimated_price_per_kg=0.0,
                    currency=request_currency,
                    min_price_per_kg=None,
                    max_price_per_kg=None,
                    used_external_context=False,
                    external_context=None,
                    external_sources=[],
                    confidence=0.0,
                    tier_used="unavailable",
                    local_report_count=0,
                    city_report_count=0,
                    country_report_count=0,
                )
                logger.info(
                    "No market data or seed for material='%s' market=(currency='%s', country='%s') "
                    "-> unavailable (no estimate)",
                    material_val,
                    request_currency,
                    request_country_part,
                )
                return res

        observed_prices = local_prices or city_prices or country_prices
        if observed_prices:
            min_observed: Optional[float] = round(min(observed_prices), 2)
            max_observed: Optional[float] = round(max(observed_prices), 2)
        elif seed is not None:
            min_observed = round(seed, 2)
            max_observed = round(seed, 2)
        else:
            min_observed = None
            max_observed = None

        external_context = None
        external_sources: list[str] = []
        use_external = (
            settings.USE_TAVILY_FALLBACK
            and bool(settings.TAVILY_API_KEY.strip())
            and conf < settings.LOW_CONFIDENCE_THRESHOLD
        )
        if use_external:
            try:
                # Lazy import keeps the deterministic estimator usable in
                # lightweight scripts without loading the full agent stack.
                from app.agent.tools.tavily_search import search_scrap_market_news

                place_bits = [display_location]
                if request_city_part and request_city_part.lower() != display_location.lower():
                    place_bits.append(request_city_part)
                if request_country_part:
                    place_bits.append(request_country_part)
                query = f"{material_val} in {', '.join([b for b in place_bits if b and b.lower() != 'unknown'] or ['unknown market'])}"
                market = search_scrap_market_news(query)
                external_context = market.get("answer") or (
                    market.get("results", [{}])[0].get("content")
                    if market.get("results")
                    else None
                )
                external_sources = [
                    result["url"]
                    for result in market.get("results", [])
                    if result.get("url")
                ]
            except Exception:
                logger.warning("Tavily fallback failed; keeping deterministic estimate", exc_info=True)

        res = PriceEstimate(
            material_type=material,
            location=display_location,
            estimated_price_per_kg=round(price, 2),
            currency=request_currency,
            min_price_per_kg=min_observed,
            max_price_per_kg=max_observed,
            used_external_context=bool(external_context),
            external_context=external_context,
            external_sources=external_sources,
            confidence=round(conf, 3),
            tier_used=tier,
            local_report_count=n_local,
            city_report_count=n_city,
            country_report_count=n_country,
        )
        logger.info(
            "Price estimate result: material='%s' location='%s' market=(currency='%s', country='%s', city='%s') "
            "-> price=%.2f %s/kg, confidence=%.3f, tier='%s' (n_local=%d, n_city=%d, n_country=%d)",
            material_val,
            display_location,
            request_currency,
            request_country_part,
            request_city_part,
            res.estimated_price_per_kg,
            request_currency,
            res.confidence,
            res.tier_used,
            n_local,
            n_city,
            n_country,
        )
        return res

    def estimate_price(
        self,
        material_str: str,
        location: str,
        currency: str = UNKNOWN_CURRENCY,
        country: Optional[str] = None,
        city: Optional[str] = None,
        neighborhood: Optional[str] = None,
    ) -> Union[PriceEstimate, dict]:
        """Estimate scrap price per kg for a material in the requested market.

        Uses the caller's local market and currency; never assumes one
        market and never converts currencies.
        """
        logger.info("Service 'estimate_price' called: material_str='%s', location='%s'", material_str, location)
        try:
            material = MaterialType(material_str.lower().strip())
        except ValueError:
            logger.warning("Service 'estimate_price' failed: unknown material '%s'", material_str)
            return {"error": f"unknown material '{material_str}'. Known: {[m.value for m in MaterialType]}"}

        return self.estimate(material, location, self.repo.trusted_reports(), currency, country, city, neighborhood)


price_estimator_service = PriceEstimatorService()

# Standalone function exports for full backwards compatibility
def estimate(
    material: MaterialType,
    location: str,
    reports: list[PriceReport],
    currency: str = UNKNOWN_CURRENCY,
    country: Optional[str] = None,
    city: Optional[str] = None,
    neighborhood: Optional[str] = None,
) -> PriceEstimate:
    return price_estimator_service.estimate(material, location, reports, currency, country, city, neighborhood)


def estimate_price(
    material_str: str,
    location: str,
    currency: str = UNKNOWN_CURRENCY,
    country: Optional[str] = None,
    city: Optional[str] = None,
    neighborhood: Optional[str] = None,
) -> Union[PriceEstimate, dict]:
    return price_estimator_service.estimate_price(material_str, location, currency, country, city, neighborhood)
