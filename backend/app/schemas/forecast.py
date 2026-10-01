"""
Price forecasting schemas for Scrapwisest (Step 11).

Leakage-free forecasting foundation over the Step 10 observational history.

A forecast answers: "Given the trustworthy historical observations available
at the forecast origin, what is a simple baseline expectation for the next
few days in this exact market/location?"

Invariants (mirroring the historical-trend layer):

- Training data is ACCEPTED reports only, aggregated into daily buckets over
  ``price_per_kg`` (never raw ``total_price``). Seeds never train.
- Market isolation via the single canonical ``market_key(country, currency)``.
  No conversion, no cross-market pooling (500 PKR != 500 INR).
- Explicit geographic scopes only (``neighborhood`` | ``city`` | ``country``)
  with NO silent broadening. A scope without enough history returns
  ``insufficient_history`` instead of training on a broader population (this
  differs deliberately from the current-price estimator's fallback chain).
- ``status`` distinguishes "no forecast" from a zero price. A missing
  forecast is ``points=[]`` with ``status`` of ``no_history`` /
  ``insufficient_history`` / ``invalid_request`` / ``unavailable`` -- never a
  fabricated ``0.0`` price point.
- No confidence score is reported. ``validation_mae`` (when computable from
  a genuine chronological holdout) is a diagnostic error metric, not a
  confidence claim.
"""

from __future__ import annotations

import datetime as _dt
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.market import UNKNOWN_CURRENCY
from app.schemas.report import MaterialType

#: Explicit forecast availability states. ``0 price`` is NOT the same thing
#: as ``no forecast available`` -- every non-ready state returns ``points=[]``.
ForecastStatus = Literal[
    "ready", "insufficient_history", "no_history", "invalid_request", "unavailable"
]


class ForecastPoint(BaseModel):
    """One forecasted day (UTC date, predicted price per kg)."""

    date: _dt.date = Field(description="UTC calendar date forecasted (inclusive)")
    predicted_price: float = Field(
        description="Baseline predicted price_per_kg for this day"
    )


class ForecastResult(BaseModel):
    """Baseline forecast for one material + market + scope + horizon.

    Scope is explicit (no silent broadening)::

        "neighborhood" -> same neighborhood + city + country + market
        "city"         -> same city + country + market
        "country"      -> whole market (same material + country + currency)

    ``source`` is always ``"reports"`` -- seeds are NEVER training data and
    never appear as forecast points. ``model`` names the baseline that
    generated the points (initially ``"moving_average"`` only).

    Freshness vs history: ``REPORT_FRESHNESS_DAYS`` (current-estimate
    recency) is deliberately NOT applied. Training uses the explicit
    ``FORECAST_TRAINING_WINDOW_DAYS`` window ending at the forecast origin
    (``historical_end``), so a report stale for today's estimate can still be
    valid training data inside the window.
    """

    material_type: MaterialType
    currency: str = UNKNOWN_CURRENCY
    country: Optional[str] = None
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    scope: Literal["neighborhood", "city", "country"] = Field(
        description="neighborhood | city | country"
    )
    status: ForecastStatus = Field(
        description="ready | insufficient_history | no_history | invalid_request | unavailable"
    )
    source: Literal["reports"] = Field(
        default="reports",
        description="Always 'reports' -- seeds never train forecasts",
    )
    model: str = Field(
        default="moving_average",
        description="Baseline/model that generated the points",
    )
    historical_start: Optional[_dt.date] = Field(
        default=None,
        description="First training observation date used (UTC, inclusive)",
    )
    historical_end: Optional[_dt.date] = Field(
        default=None,
        description="Forecast origin: last training observation date used (UTC, inclusive)",
    )
    forecast_start: Optional[_dt.date] = Field(
        default=None, description="First forecasted date (UTC, historical_end + 1 day)"
    )
    forecast_end: Optional[_dt.date] = Field(
        default=None, description="Last forecasted date (UTC, inclusive)"
    )
    horizon_days: int = Field(
        ge=0, description="Number of future days forecasted (0 when not ready)"
    )
    training_report_count: int = Field(
        ge=0,
        description="Eligible ACCEPTED reports inside the training window",
    )
    training_points: int = Field(
        ge=0, description="Daily training buckets actually used (oldest -> newest)"
    )
    validation_mae: Optional[float] = Field(
        default=None,
        description=(
            "Mean absolute error of the baseline on a chronological holdout "
            "(diagnostic only, never a confidence score; None when the history "
            "is too short for a genuine holdout)"
        ),
    )
    validation_points: int = Field(
        ge=0,
        default=0,
        description="Holdout daily buckets used for validation_mae (0 when none)",
    )
    points: List[ForecastPoint] = Field(
        default_factory=list,
        description="Forecasted days, oldest -> newest (empty unless status is ready)",
    )

    def market_key(self) -> tuple[str, str]:
        """Canonical market identity for this forecast.

        Delegates to the single ``market_key(country, currency)`` helper so
        forecasts can never invent a second market representation.
        """
        from app.schemas.market import market_key as _market_key

        return _market_key(self.country, self.currency)
