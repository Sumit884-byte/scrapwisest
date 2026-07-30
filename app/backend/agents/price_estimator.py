"""
Price estimator for ScrapSense.

Three-tier fallback chain — pure math, no LLM:
  Tier 1 (local)     — median of recent reports for this material in this neighborhood
  Tier 2 (city-wide) — median across all neighborhoods in the city
  Tier 3 (seed)      — manually collected baseline prices

Tiers blend by data weight: if local has some reports but fewer than MIN_LOCAL,
it contributes proportionally alongside city-wide rather than being ignored.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.backend.agent_schemas.report import MaterialType, PriceReport

# Minimum report counts before a tier is considered reliable on its own
MIN_LOCAL = 5
MIN_CITY = 10

# Seed prices (PKR/kg) — collected from Multan kabari markets, July 2026
# Update these after each manual field visit.
SEED_PRICES: dict[MaterialType, float] = {
    MaterialType.PLASTIC_PET:      140.0,
    MaterialType.PLASTIC_HDPE:     85.0,
    MaterialType.GLASS:            8.0,
    MaterialType.METAL_ALUMINUM:   1050.0,
    MaterialType.METAL_STEEL:      195.0,
    MaterialType.CARDBOARD:        28.0,
    MaterialType.MIXED_PAPER:      42.0,
    MaterialType.OTHER:            50.0,
}


@dataclass
class PriceEstimate:
    material_type: MaterialType
    location: str
    estimated_price_per_kg: float
    confidence: float          # 0–1; higher = more real data backing it
    tier_used: str             # "local" | "city" | "seed" | "local+city"
    local_report_count: int
    city_report_count: int


def estimate(
    material: MaterialType,
    location: str,
    reports: list[PriceReport],
) -> PriceEstimate:
    """
    material  — what the picker is selling
    location  — neighborhood name (matched against report.location)
    reports   — trusted reports for this city (anomaly-cleared; caller pre-filters by city)
    """
    relevant = [
        r for r in reports
        if r.material_type == material and not r.needs_confirmation
    ]

    local = [r for r in relevant if r.location.lower() == location.lower()]
    city_wide = relevant

    local_prices = [r.price_paid_pkr_per_kg for r in local]
    city_prices  = [r.price_paid_pkr_per_kg for r in city_wide]
    seed         = SEED_PRICES[material]

    n_local = len(local_prices)
    n_city  = len(city_prices)

    if n_local >= MIN_LOCAL and n_city >= MIN_CITY:
        local_w = n_local / (n_local + n_city)
        city_w  = 1.0 - local_w
        price   = local_w * statistics.median(local_prices) + city_w * statistics.median(city_prices)
        conf    = min(0.95, 0.6 + 0.35 * (n_local / (MIN_LOCAL * 2)))
        tier    = "local+city"

    elif n_local >= MIN_LOCAL:
        price = statistics.median(local_prices)
        conf  = min(0.90, 0.55 + 0.35 * (n_local / (MIN_LOCAL * 3)))
        tier  = "local"

    elif n_city >= MIN_CITY:
        city_med = statistics.median(city_prices)
        city_w   = min(0.85, n_city / (MIN_CITY * 2))
        price    = city_w * city_med + (1.0 - city_w) * seed
        conf     = min(0.70, 0.35 + 0.35 * (n_city / (MIN_CITY * 2)))
        tier     = "city"

    elif n_local > 0 or n_city > 0:
        prices   = local_prices or city_prices
        data_med = statistics.median(prices)
        n        = len(prices)
        data_w   = n / (MIN_LOCAL if local_prices else MIN_CITY)
        price    = data_w * data_med + (1.0 - data_w) * seed
        conf     = 0.20 + 0.15 * data_w
        tier     = "local" if local_prices else "city"

    else:
        price = seed
        conf  = 0.20
        tier  = "seed"

    return PriceEstimate(
        material_type=material,
        location=location,
        estimated_price_per_kg=round(price, 2),
        confidence=round(conf, 3),
        tier_used=tier,
        local_report_count=n_local,
        city_report_count=n_city,
    )
