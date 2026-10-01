"""
Historical price trend schemas for Scrapwisest (Step 10).

Observational time-series only -- no forecasting, no confidence, no seeds.

A trend answers: "How has this material's reported price changed over a
specified historical period in this market/location?"

Each point is a daily aggregation of real ACCEPTED reports in the SAME
market (``market_key(country, currency)``) and the SAME explicit
geographic scope. Seeds never create points; missing days stay missing.
"""

from __future__ import annotations

import datetime as _dt
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.market import UNKNOWN_CURRENCY
from app.schemas.report import MaterialType


class HistoricalPricePoint(BaseModel):
    """One daily bucket of observed prices (UTC date)."""

    date: _dt.date = Field(description="UTC calendar date for this bucket (inclusive)")
    average_price: float = Field(description="Mean price_per_kg for this day")
    min_price: float = Field(description="Minimum price_per_kg observed this day")
    max_price: float = Field(description="Maximum price_per_kg observed this day")
    median_price: float = Field(description="Median price_per_kg observed this day")
    report_count: int = Field(ge=0, description="Accepted reports in this bucket")


class HistoricalPriceTrend(BaseModel):
    """Daily historical series for one material + market + scope + range.

    Scope is explicit (no silent broadening)::

        "neighborhood" -> same neighborhood + city + country + market
        "city"         -> same city + country + market
        "country"      -> whole market (same material + country + currency)

    ``source`` is always ``"reports"`` -- seeds are NEVER historical
    evidence. Empty history is ``points=[]`` with ``report_count=0``;
    no price is fabricated.
    """

    material_type: MaterialType
    currency: str = UNKNOWN_CURRENCY
    country: Optional[str] = None
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    scope: Literal["neighborhood", "city", "country"] = Field(
        description="neighborhood | city | country"
    )
    source: Literal["reports"] = Field(
        default="reports", description="Always 'reports' -- seeds never create history"
    )
    start_date: Optional[_dt.date] = Field(
        default=None, description="Inclusive requested range start (UTC date)"
    )
    end_date: Optional[_dt.date] = Field(
        default=None, description="Inclusive requested range end (UTC date)"
    )
    report_count: int = Field(
        ge=0, description="Total eligible accepted reports across all points"
    )
    points: List[HistoricalPricePoint] = Field(
        default_factory=list,
        description="Daily buckets with actual observations, oldest -> newest",
    )

    def market_key(self) -> tuple[str, str]:
        """Canonical market identity for this trend.

        Delegates to the single ``market_key(country, currency)`` helper so
        trends can never invent a second market representation.
        """
        from app.schemas.market import market_key as _market_key

        return _market_key(self.country, self.currency)
