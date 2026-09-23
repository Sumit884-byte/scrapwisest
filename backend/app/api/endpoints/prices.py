"""
Prices endpoints: estimate scrap price benchmarks per material and location.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Query

from app.schemas.price import PriceEstimateResponse
from app.schemas.report import MaterialType
from app.services.location_resolver import UNKNOWN_CURRENCY
from app.services.price_estimator import price_estimator_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prices", tags=["prices"])


@router.get("/estimate", response_model=PriceEstimateResponse)
async def get_price_estimate(
    material: str = Query(..., description="Scrap material type (e.g. plastic_pet, metal_aluminum)"),
    location: str = Query(..., description="Neighborhood or city area name (e.g. Income Colony)"),
    currency: str | None = Query(None, description="ISO 4217 currency code for the requested market (e.g. PKR, INR, USD)"),
    country: str | None = Query(None, description="Country for the requested market (e.g. Pakistan)"),
    city: str | None = Query(None, description="City for the requested market (e.g. Multan)"),
    neighborhood: str | None = Query(None, description="Neighborhood within the city (e.g. Income Colony)"),
):
    """
    Returns the estimated price per kg for a given scrap material in the
    requested market. Uses the market/location-scoped fallback chain
    (neighborhood -> city -> country/market -> market-specific seed) in the
    requested market's currency. No currency conversion is performed.
    """
    logger.info(
        "API request GET /prices/estimate: material='%s', location='%s', currency='%s', country='%s', city='%s', neighborhood='%s'",
        material,
        location,
        currency,
        country,
        city,
        neighborhood,
    )
    try:
        mat_enum = MaterialType(material.strip().lower())
    except ValueError:
        known = [m.value for m in MaterialType]
        raise HTTPException(
            status_code=400,
            detail=f"Unknown material '{material}'. Available materials: {known}",
        )

    estimate = price_estimator_service.estimate(
        mat_enum,
        location,
        currency=currency or UNKNOWN_CURRENCY,
        country=country,
        city=city,
        neighborhood=neighborhood,
    )
    return estimate
