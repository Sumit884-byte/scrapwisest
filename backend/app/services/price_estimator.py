"""
Price Estimator service for Scrapwisest.
Implements the 3-tier fallback pricing chain, scoped to one market_key:
  Tier 1 (local)     — median of recent reports for this material in this neighborhood
  Tier 2 (city-wide) — median across neighborhoods in the same currency/country/city
  Tier 3 (seed)      — baseline for that currency
"""

from __future__ import annotations

import logging
import statistics
from typing import List, Optional, Union

from app.core.config import settings
from app.repositories.report_repository import ReportRepository, report_repo
from app.schemas.market import (
    UNKNOWN_CURRENCY,
    canonicalize_country,
    market_key,
    normalize_currency,
    normalize_place_part,
)
from app.schemas.price import PriceEstimate
from app.schemas.report import MaterialType, PriceReport
from app.services.location_resolver import normalize_location

logger = logging.getLogger(__name__)

SEED_PRICES: dict[MaterialType, float] = {
    MaterialType(key): value for key, value in settings.SEED_PRICES.items()
}


def seed_price_for(material: MaterialType, currency: str) -> Optional[float]:
    table = settings.SEED_PRICES_BY_CURRENCY.get(normalize_currency(currency), {})
    key = material.value if hasattr(material, "value") else str(material)
    return table.get(key)


def price_band_for(material: MaterialType | str, currency: str) -> Optional[tuple[float, float]]:
    table = settings.PRICE_BANDS_BY_CURRENCY.get(normalize_currency(currency), {})
    key = material.value if hasattr(material, "value") else str(material)
    return table.get(key)


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
        country: str | None = None,
        city: str | None = None,
    ) -> PriceEstimate:
        """Calculate a scrap price using only reports from the same market."""
        if reports is None:
            reports = self.repo.trusted_reports()

        currency = normalize_currency(currency)
        country = canonicalize_country(country)
        city = normalize_place_part(city)
        location = normalize_location(location)
        wanted = market_key(currency, country, city)

        logger.info(
            "Calculating price estimate for material='%s' location='%s' market=%s",
            material.value,
            location,
            wanted,
        )
        relevant = [
            report
            for report in reports
            if report.material_type == material
            and not report.needs_confirmation
            and report.market_key() == wanted
        ]

        local = [
            report
            for report in relevant
            if normalize_location(report.location) == location
            or (
                report.neighborhood
                and normalize_location(report.neighborhood) == location
            )
        ]
        city_wide = relevant

        local_prices = [report.price_per_kg for report in local]
        city_prices = [report.price_per_kg for report in city_wide]
        seed = seed_price_for(material, currency)
        if seed is None:
            seed = 0.0

        n_local = len(local_prices)
        n_city = len(city_prices)

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
            city_w = min(0.85, n_city / (self.min_city * 2))
            price = city_w * city_med + (1.0 - city_w) * seed if seed else city_med
            conf = min(0.70, 0.35 + 0.35 * (n_city / (self.min_city * 2)))
            tier = "city"
        elif n_local > 0 or n_city > 0:
            prices = local_prices or city_prices
            data_med = statistics.median(prices)
            n = len(prices)
            data_w = n / (self.min_local if local_prices else self.min_city)
            price = data_w * data_med + (1.0 - data_w) * seed if seed else data_med
            conf = 0.20 + 0.15 * min(1.0, data_w)
            tier = "local" if local_prices else "city"
        else:
            price = seed
            conf = 0.20 if seed else 0.05
            tier = "seed"

        observed_prices = local_prices or city_prices
        fallback = seed if seed else 0.0
        min_observed = round(min(observed_prices), 2) if observed_prices else round(fallback, 2)
        max_observed = round(max(observed_prices), 2) if observed_prices else round(fallback, 2)

        external_context = None
        external_sources: list[str] = []
        use_external = (
            settings.USE_TAVILY_FALLBACK
            and bool(settings.TAVILY_API_KEY.strip())
            and conf < settings.LOW_CONFIDENCE_THRESHOLD
        )
        if use_external:
            try:
                from app.agent.tools.tavily_search import search_scrap_market_news

                place = ", ".join(part for part in (city or location, country) if part)
                query = f"{material.value} scrap price per kg in {place or location} {currency}"
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
            location=location,
            estimated_price_per_kg=round(price, 2),
            currency=currency,
            min_price_per_kg=min_observed,
            max_price_per_kg=max_observed,
            used_external_context=bool(external_context),
            external_context=external_context,
            external_sources=external_sources,
            confidence=round(conf, 3),
            tier_used=tier,
            local_report_count=n_local,
            city_report_count=n_city,
        )
        logger.info(
            "Price estimate result: material='%s' location='%s' -> price=%.2f %s/kg, confidence=%.3f, tier='%s' (n_local=%d, n_city=%d)",
            material.value,
            location,
            res.estimated_price_per_kg,
            currency,
            res.confidence,
            res.tier_used,
            res.local_report_count,
            res.city_report_count,
        )
        return res

    def estimate_price(
        self,
        material_str: str,
        location: str,
        currency: str = UNKNOWN_CURRENCY,
        country: str | None = None,
        city: str | None = None,
    ) -> Union[PriceEstimate, dict]:
        """Estimate scrap price per kg for a material in a location (string-based tool interface)."""
        logger.info(
            "Service 'estimate_price' called: material_str='%s', location='%s', currency='%s'",
            material_str,
            location,
            currency,
        )
        try:
            material = MaterialType(material_str.lower().strip())
        except ValueError:
            logger.warning("Service 'estimate_price' failed: unknown material '%s'", material_str)
            return {"error": f"unknown material '{material_str}'. Known: {[m.value for m in MaterialType]}"}

        return self.estimate(
            material,
            location,
            self.repo.trusted_reports(),
            currency,
            country=country,
            city=city,
        )


price_estimator_service = PriceEstimatorService()


def estimate(
    material: MaterialType,
    location: str,
    reports: list[PriceReport],
    currency: str = UNKNOWN_CURRENCY,
    country: str | None = None,
    city: str | None = None,
) -> PriceEstimate:
    return price_estimator_service.estimate(
        material, location, reports, currency, country=country, city=city
    )


def estimate_price(
    material_str: str,
    location: str,
    currency: str = UNKNOWN_CURRENCY,
    country: str | None = None,
    city: str | None = None,
) -> Union[PriceEstimate, dict]:
    return price_estimator_service.estimate_price(
        material_str, location, currency, country=country, city=city
    )
