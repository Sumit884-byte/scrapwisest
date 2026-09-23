"""
Pydantic schemas for price estimation requests and responses.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.market import UNKNOWN_CURRENCY
from app.schemas.report import MaterialType


class PriceEstimate(BaseModel):
    material_type: MaterialType
    location: str
    estimated_price_per_kg: float
    # Currency the estimate is denominated in. "unknown" for legacy flows
    # that never named one; always the requested market's currency -- the
    # estimator never converts between currencies.
    currency: str = UNKNOWN_CURRENCY
    min_price_per_kg: Optional[float] = None
    max_price_per_kg: Optional[float] = None
    used_external_context: bool = False
    external_context: Optional[str] = None
    external_sources: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    tier_used: str  # "local" (neighborhood) | "local+city" | "city" | "country" | "seed" | "unavailable"
    local_report_count: int
    city_report_count: int
    # Reports pooled at the country/market scope (same material, currency,
    # and country). Defaults to 0 so older stored payloads still parse.
    country_report_count: int = 0


class PriceEstimateRequest(BaseModel):
    material: str
    location: str


class PriceEstimateResponse(PriceEstimate):
    pass
