"""
Prices endpoints: estimate scrap price benchmarks per material and location.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Query

from app.schemas.price import PriceEstimateResponse
from app.schemas.report import MaterialType
from app.services.price_estimator import price_estimator_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prices", tags=["prices"])


@router.get("/estimate", response_model=PriceEstimateResponse)
async def get_price_estimate(
    material: str = Query(..., description="Scrap material type (e.g. plastic_pet, metal_aluminum)"),
    location: str = Query(..., description="Neighborhood or city area name (e.g. Income Colony)"),
):
    """
    Returns the estimated price per kg for a given scrap material in a specific area.
    Uses 3-tier fallback algorithm (neighborhood median -> city-wide median -> seed baseline).
    """
    logger.info("API request GET /prices/estimate: material='%s', location='%s'", material, location)
    try:
        mat_enum = MaterialType(material.strip().lower())
    except ValueError:
        known = [m.value for m in MaterialType]
        raise HTTPException(
            status_code=400,
            detail=f"Unknown material '{material}'. Available materials: {known}",
        )

    estimate = price_estimator_service.estimate(mat_enum, location)
    return estimate
