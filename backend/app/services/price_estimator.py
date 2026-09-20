"""
Price Estimator service for ScrapSense.
Implements the 3-tier fallback pricing chain:
  Tier 1 (local)     — median of recent reports for this material in this neighborhood
  Tier 2 (city-wide) — median across all neighborhoods in the city
  Tier 3 (seed)      — manually collected baseline prices
"""

from __future__ import annotations

import logging
import statistics
from typing import List, Optional, Union

from app.core.config import settings
from app.repositories.report_repository import ReportRepository, report_repo
from app.schemas.price import PriceEstimate
from app.schemas.report import MaterialType, PriceReport

logger = logging.getLogger(__name__)

# Seed prices (PKR/kg) as MaterialType enum mapping
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
    ) -> PriceEstimate:
        """
        Calculates scrap price estimate using the 3-tier fallback algorithm.
        """
        if reports is None:
            reports = self.repo.trusted_reports()

        logger.info("Calculating price estimate for material='%s' location='%s'", material.value, location)
        relevant = [
            r for r in reports
            if r.material_type == material and not r.needs_confirmation
        ]

        local = [r for r in relevant if r.location.strip().lower() == location.strip().lower()]
        city_wide = relevant

        local_prices = [r.price_paid_pkr_per_kg for r in local]
        city_prices = [r.price_paid_pkr_per_kg for r in city_wide]
        seed = self.seed_prices.get(material, 50.0)

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
            price = city_w * city_med + (1.0 - city_w) * seed
            conf = min(0.70, 0.35 + 0.35 * (n_city / (self.min_city * 2)))
            tier = "city"

        elif n_local > 0 or n_city > 0:
            prices = local_prices or city_prices
            data_med = statistics.median(prices)
            n = len(prices)
            data_w = n / (self.min_local if local_prices else self.min_city)
            price = data_w * data_med + (1.0 - data_w) * seed
            conf = 0.20 + 0.15 * data_w
            tier = "local" if local_prices else "city"

        else:
            price = seed
            conf = 0.20
            tier = "seed"

        res = PriceEstimate(
            material_type=material,
            location=location,
            estimated_price_per_kg=round(price, 2),
            confidence=round(conf, 3),
            tier_used=tier,
            local_report_count=n_local,
            city_report_count=n_city,
        )
        logger.info(
            "Price estimate result: material='%s' location='%s' -> price=%.2f PKR/kg, confidence=%.3f, tier='%s' (n_local=%d, n_city=%d)",
            material.value,
            location,
            res.estimated_price_per_kg,
            res.confidence,
            res.tier_used,
            res.local_report_count,
            res.city_report_count,
        )
        return res

    def estimate_price(self, material_str: str, location: str) -> Union[PriceEstimate, dict]:
        """Estimate scrap price per kg for a material in a location (string-based tool interface)."""
        logger.info("Service 'estimate_price' called: material_str='%s', location='%s'", material_str, location)
        try:
            material = MaterialType(material_str.lower().strip())
        except ValueError:
            logger.warning("Service 'estimate_price' failed: unknown material '%s'", material_str)
            return {"error": f"unknown material '{material_str}'. Known: {[m.value for m in MaterialType]}"}

        return self.estimate(material, location, self.repo.trusted_reports())


price_estimator_service = PriceEstimatorService()

# Standalone function exports for full backwards compatibility
def estimate(material: MaterialType, location: str, reports: list[PriceReport]) -> PriceEstimate:
    return price_estimator_service.estimate(material, location, reports)


def estimate_price(material_str: str, location: str) -> Union[PriceEstimate, dict]:
    return price_estimator_service.estimate_price(material_str, location)
