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
from datetime import datetime
from typing import List, Optional, Union

from app.core.config import settings
from app.repositories.report_repository import ReportRepository, report_repo
from app.services.report_freshness import filter_fresh_reports
from app.schemas.market import UNKNOWN_CURRENCY, market_key
from app.schemas.price import PriceEstimate, PriceEvidence
from app.schemas.report import MaterialType, PriceReport
from app.services.location_resolver import (
    neighborhood_label,
    normalize_currency,
    normalize_location,
    normalize_place_part,
    same_city,
)

logger = logging.getLogger(__name__)

# Single source of truth: ``app.core.config.settings`` owns SEED_PRICES and
# PRICE_PER_KG_BANDS for the verified Pakistan/PKR market only.
# Cleanup: removed duplicated _SEED_BY_MARKET/_BAND_BY_MARKET caches here.
# Helpers below delegate to ``settings.seed_price_for/price_band_for``
# (canonical ``market_key`` identity) plus the documented legacy-unknown
# fallback. No behavior change, no new values, no conversion.
_VERIFIED_SEED_MARKET: tuple[str, str] = market_key(
    settings.SEED_MARKET_COUNTRY, settings.SEED_MARKET_CURRENCY
)

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

    Delegates to ``settings.seed_price_for`` (single source of truth).
    Legacy unknown market ``("unknown", "")`` falls back to the verified
    Pakistan/PKR seed for backwards compatibility. All other markets
    return None. Never converts, never fabricates.
    """
    direct = settings.seed_price_for(material, country, currency)
    if direct is not None:
        return direct
    if market_key(country, currency) == _LEGACY_SEED_MARKET:
        return settings.SEED_PRICES.get(_material_value(material))
    return None


def _band_for(
    material: MaterialType | str, country: str | None, currency: str | None
) -> Optional[tuple[float, float]]:
    """Verified sanity band for ``(material, market)``, or None.

    Delegates to ``settings.price_band_for`` (single source of truth).
    Legacy unknown market falls back to the verified Pakistan/PKR band.
    Explicit foreign markets return None. Never converts.
    """
    direct = settings.price_band_for(material, country, currency)
    if direct is not None:
        return direct
    if market_key(country, currency) == _LEGACY_SEED_MARKET:
        raw = settings.PRICE_PER_KG_BANDS.get(_material_value(material))
        return tuple(raw) if raw is not None else None
    return None


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

    Step 8: only ACCEPTED (trusted) reports are market data -- PENDING and
    REJECTED reports are excluded here even when a caller passes an
    unfiltered list. Uses the canonical ``is_trusted_report`` helper so
    trust has exactly one implementation. Currency must always match
    exactly (never mix PKR/INR/USD). Country must match exactly when the
    request names one; a request that names no country is treated as a
    legacy wildcard for that dimension only, so old callers that pass just
    a location string keep working while never mixing currencies.
    """
    if _material_value(report.material_type) != material_val:
        return False
    from app.services.report_trust import is_trusted_report

    if not is_trusted_report(report):
        return False
    if normalize_currency(report.currency) != request_currency:
        return False
    if request_country is None:
        return True
    report_country = normalize_place_part(report.country)
    return (report_country or "").lower() == request_country.lower()


def _applied_freshness_days(freshness_days: Optional[int]) -> int:
    """Freshness window (days) actually applied to this estimate.

    Single rule: explicit override wins, otherwise the configured
    ``REPORT_FRESHNESS_DAYS``. Mirrors ``report_freshness._resolve_window``
    without importing private helpers, so evidence always names the window
    the estimator filtered with.
    """
    if freshness_days is None:
        return int(settings.REPORT_FRESHNESS_DAYS)
    return int(freshness_days)


def _make_evidence(
    *,
    source: str,
    scope: str,
    report_count: int,
    currency: str,
    country: Optional[str],
    freshness_days: int,
    seed_source: Optional[str] = None,
) -> PriceEvidence:
    """Build Step 9 evidence with the canonical market identity.

    ``currency``/``country`` are the estimator's already-normalized request
    values, so ``evidence.market_key()`` always equals the market the pools
    were filtered with -- no second market representation, no conversion.
    """
    return PriceEvidence(
        source=source,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        report_count=int(report_count),
        currency=currency,
        country=country,
        freshness_days=int(freshness_days),
        seed_source=seed_source,
    )


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
        now: Optional[datetime] = None,
        freshness_days: Optional[int] = None,
    ) -> PriceEstimate:
        """
        Market- and location-scoped scrap price estimate.

        Pools only ACCEPTED + FRESH reports for the same material in the
        same market (same currency, and same country when the request names
        one), then falls back neighborhood -> city -> country/market ->
        market-specific seed. PENDING/REJECTED reports never contribute,
        even when passed directly; stale reports (older than the freshness
        window) never contribute to a current estimate; when no fresh
        trusted reports exist the market-specific seed (or ``unavailable``)
        applies. Seeds themselves never expire. Use the requested market's
        local currency; never convert currencies.

        Step 9: every result carries ``evidence`` built from the SAME
        eligible pools that priced it (source/scope/report_count/market/
        freshness_days/seed_source). Confidence formulas are preserved
        exactly; seed reports ``source="seed"`` with ``report_count=0`` and
        ``unavailable`` reports ``source="unavailable"`` with
        ``confidence=0``.
        """
        if reports is None:
            reports = self.repo.trusted_reports()

        # Step 7: recency-aware population. Filter to fresh reports FIRST so
        # a stale neighborhood pool cannot block a fresher city fallback --
        # location tiers below only ever see current data. Counts reported
        # in the response therefore reflect usable (fresh) reports only.
        # Step 8: trust is enforced in _report_matches_market via the
        # canonical is_trusted_report helper, so the final pool is
        # ACCEPTED + fresh even when callers pass unfiltered lists.
        reports = filter_fresh_reports(reports, now=now, freshness_days=freshness_days)

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

        # Step 9: evidence window is the same freshness window the pools
        # above were filtered with (explicit override or configured default).
        applied_freshness = _applied_freshness_days(freshness_days)

        # Step 9 evidence placeholders -- set on every branch below from the
        # SAME eligible pools that price the estimate (accepted + fresh +
        # same material/market/scope). Confidence math below is preserved
        # exactly; only evidence metadata is added.
        ev_source = "reports"
        ev_scope = "neighborhood"
        ev_count = 0
        ev_seed_source: Optional[str] = None

        if n_local >= self.min_local and n_city >= self.min_city:
            local_w = n_local / (n_local + n_city)
            city_w = 1.0 - local_w
            price = local_w * statistics.median(local_prices) + city_w * statistics.median(city_prices)
            conf = min(0.95, 0.6 + 0.35 * (n_local / (self.min_local * 2)))
            tier = "local+city"
            # Blended neighborhood + city medians. Pools are nested
            # (neighborhood ⊆ city), so the distinct supporting reports are
            # the city pool -- never n_local + n_city (no double-count).
            ev_source = "reports"
            ev_scope = "neighborhood+city"
            ev_count = n_city
            ev_seed_source = None

        elif n_local >= self.min_local:
            price = statistics.median(local_prices)
            conf = min(0.90, 0.55 + 0.35 * (n_local / (self.min_local * 3)))
            tier = "local"
            ev_source = "reports"
            ev_scope = "neighborhood"
            ev_count = n_local
            ev_seed_source = None

        elif n_city >= self.min_city:
            city_med = statistics.median(city_prices)
            if seed is not None:
                city_w = min(0.85, n_city / (self.min_city * 2))
                price = city_w * city_med + (1.0 - city_w) * seed
            else:
                price = city_med
            conf = min(0.70, 0.35 + 0.35 * (n_city / (self.min_city * 2)))
            tier = "city"
            # Reports supported the number even when blended with the seed;
            # only the pure no-report fallback is source="seed".
            ev_source = "reports"
            ev_scope = "city"
            ev_count = n_city
            ev_seed_source = None

        elif n_country >= self.min_city:
            country_med = statistics.median(country_prices)
            if seed is not None:
                country_w = min(0.85, n_country / (self.min_city * 2))
                price = country_w * country_med + (1.0 - country_w) * seed
            else:
                price = country_med
            conf = min(0.70, 0.35 + 0.35 * (n_country / (self.min_city * 2)))
            tier = "country"
            ev_source = "reports"
            ev_scope = "country"
            ev_count = n_country
            ev_seed_source = None

        elif n_local > 0 or n_city > 0 or n_country > 0:
            if local_prices:
                prices = local_prices
                threshold = self.min_local
                tier = "local"
                ev_scope = "neighborhood"
            elif city_prices:
                prices = city_prices
                threshold = self.min_city
                tier = "city"
                ev_scope = "city"
            else:
                prices = country_prices
                threshold = self.min_city
                tier = "country"
                ev_scope = "country"
            data_med = statistics.median(prices)
            n = len(prices)
            data_w = n / threshold
            if seed is not None:
                price = data_w * data_med + (1.0 - data_w) * seed
            else:
                price = data_med
            conf = 0.20 + 0.15 * data_w
            # Thin-data tier still comes from real reports (seed-blended or
            # not); report_count is the distinct thin pool that priced it.
            ev_source = "reports"
            ev_count = n
            ev_seed_source = None

        else:
            if seed is not None:
                price = seed
                conf = 0.20
                tier = "seed"
                ev_source = "seed"
                ev_scope = "seed"
                ev_count = 0
                ev_seed_source = settings.SEED_SOURCE
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
                    evidence=_make_evidence(
                        source="unavailable",
                        scope="unavailable",
                        report_count=0,
                        currency=request_currency,
                        country=request_country_part,
                        freshness_days=applied_freshness,
                        seed_source=None,
                    ),
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
            evidence=_make_evidence(
                source=ev_source,
                scope=ev_scope,
                report_count=ev_count,
                currency=request_currency,
                country=request_country_part,
                freshness_days=applied_freshness,
                seed_source=ev_seed_source,
            ),
        )
        logger.info(
            "Price estimate result: material='%s' location='%s' market=(currency='%s', country='%s', city='%s') "
            "-> price=%.2f %s/kg, confidence=%.3f, tier='%s' (n_local=%d, n_city=%d, n_country=%d) "
            "evidence=(source=%s, scope=%s, report_count=%d, freshness=%dd)",
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
            ev_source,
            ev_scope,
            ev_count,
            applied_freshness,
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
        now: Optional[datetime] = None,
        freshness_days: Optional[int] = None,
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

        return self.estimate(
            material, location, self.repo.trusted_reports(), currency, country, city, neighborhood, now, freshness_days
        )


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
    now: Optional[datetime] = None,
    freshness_days: Optional[int] = None,
) -> PriceEstimate:
    return price_estimator_service.estimate(
        material, location, reports, currency, country, city, neighborhood, now, freshness_days
    )


def estimate_price(
    material_str: str,
    location: str,
    currency: str = UNKNOWN_CURRENCY,
    country: Optional[str] = None,
    city: Optional[str] = None,
    neighborhood: Optional[str] = None,
    now: Optional[datetime] = None,
    freshness_days: Optional[int] = None,
) -> Union[PriceEstimate, dict]:
    return price_estimator_service.estimate_price(
        material_str, location, currency, country, city, neighborhood, now, freshness_days
    )
