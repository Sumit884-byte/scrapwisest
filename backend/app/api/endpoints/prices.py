"""
Prices endpoints: estimate scrap price benchmarks per material and location,
plus historical price trends (Step 10, observational only -- no forecasting).
"""

from __future__ import annotations

import logging
from datetime import date
from fastapi import APIRouter, HTTPException, Query

from app.schemas.history import HistoricalPriceTrend
from app.schemas.price import PriceEstimateResponse
from app.schemas.report import MaterialType
from app.services.location_resolver import UNKNOWN_CURRENCY
from app.services.price_estimator import price_estimator_service
from app.services.price_history import price_history_service

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


@router.get("/history", response_model=HistoricalPriceTrend)
async def get_price_history(
    material: str = Query(..., description="Scrap material type (e.g. plastic_pet, metal_aluminum)"),
    currency: str | None = Query(None, description="ISO 4217 currency code for the requested market (e.g. PKR, INR, USD)"),
    country: str | None = Query(None, description="Country for the requested market (e.g. Pakistan)"),
    city: str | None = Query(None, description="City for the requested market (e.g. Multan)"),
    neighborhood: str | None = Query(None, description="Neighborhood within the city (e.g. Income Colony)"),
    start: date | None = Query(None, description="Inclusive range start (UTC date, e.g. 2026-08-01)"),
    end: date | None = Query(None, description="Inclusive range end (UTC date, e.g. 2026-08-31)"),
):
    """
    Returns the daily historical price series for a material in the
    requested market/location scope over an explicit date range.

    Step 10 invariants: ACCEPTED reports only (PENDING/REJECTED never
    contribute); the current REPORT_FRESHNESS_DAYS window is NOT applied --
    ``start``/``end`` select the historical population instead; market
    isolation uses the canonical ``market_key(country, currency)`` with no
    conversion; scopes are explicit (neighborhood | city | country) with no
    silent broadening; seeds never create points; missing days stay missing.
    """
    logger.info(
        "API request GET /prices/history: material='%s', currency='%s', country='%s', "
        "city='%s', neighborhood='%s', start='%s', end='%s'",
        material,
        currency,
        country,
        city,
        neighborhood,
        start,
        end,
    )
    try:
        mat_enum = MaterialType(material.strip().lower())
    except ValueError:
        known = [m.value for m in MaterialType]
        raise HTTPException(
            status_code=400,
            detail=f"Unknown material '{material}'. Available materials: {known}",
        )
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date range: start ({start}) is after end ({end})",
        )
    return price_history_service.get_history(
        mat_enum,
        currency=currency or UNKNOWN_CURRENCY,
        country=country,
        city=city,
        neighborhood=neighborhood,
        start_date=start,
        end_date=end,
    )
