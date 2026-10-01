"""
Price forecasting service for Scrapwisest (Step 11).

Safe, leakage-free forecasting foundation over the Step 10 observational
history. Answers first: "Do we have enough trustworthy historical
observations to make a forecast?" -- otherwise ``insufficient_history`` /
``no_history`` with ``points=[]`` (never a fabricated price, never ``0.0``).

Training-data rules (enforced by delegating ALL filtering/aggregation to
``price_history.build_history`` so trust/market/scope/range have exactly one
implementation each):

- ACCEPTED reports only (PENDING/REJECTED never train, even when passed
  directly). Seeds NEVER train and never appear as points.
- Canonical ``market_key(country, currency)`` isolation only. No conversion,
  no cross-market pooling, no currency normalization tricks beyond the single
  ``normalize_currency`` helper every other layer uses.
- Explicit geographic scopes only (neighborhood | city | country) with NO
  silent broadening -- unlike the current-price estimator's fallback chain,
  a scope without enough history returns ``insufficient_history`` instead of
  training on a broader population.
- ``REPORT_FRESHNESS_DAYS`` (current-estimate recency) is NOT applied here.
  Training uses the explicit ``FORECAST_TRAINING_WINDOW_DAYS`` window ending
  at the forecast origin: a report stale for today's estimate is still valid
  training data inside the window.

Leakage prevention:

- The forecast origin ``T`` is the latest eligible historical observation
  (``historical_end``). An optional ``end_date`` cap excludes every
  observation ``> T`` at the filter level, so future data can never
  influence training, preprocessing, or validation.
- The training series is chronological (oldest -> newest); it is never
  reordered and partitioning is strictly by time (no chance-based splits).
- There is no scaler/normalizer at all (the baseline works directly on
  observed ``price_per_kg`` daily averages), so scaler-fit leakage is
  impossible by construction.
- Validation is a chronological holdout: the baseline is fitted on the train
  prefix only, and ``validation_mae`` is measured on the later holdout.
- Missing days stay missing: the baseline consumes observed daily buckets
  directly (no resampling, no forward-fill, no zero/seed fill).

Model (deliberately simple):

- ``MovingAverageBaseline``: ``forecast = mean of the most recent N observed
  daily average_price values`` with ``N = FORECAST_BASELINE_WINDOW``.
  Deterministic, dependency-free (stdlib ``statistics`` only -- no
  TensorFlow/PyTorch/sklearn), computed on demand with NO persistent model
  artifact. Neural forecasting (LSTM/RNN/...) is intentionally deferred: the
  available history is sparse, and a testable baseline must come first (see
  Step 11 sections 10 and 16). The ``ForecastModel`` interface keeps the
  service extensible (``moving_average`` | ``linear_trend`` | ``ARIMA`` |
  ``gradient_boosting`` | ``LSTM`` ...) without coupling the API to one
  implementation.
"""

from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timedelta
from typing import List, Optional, Protocol, Union

from app.core.config import settings
from app.repositories.report_repository import ReportRepository, report_repo
from app.schemas.forecast import ForecastPoint, ForecastResult
from app.schemas.market import UNKNOWN_CURRENCY, normalize_currency, normalize_place_part
from app.schemas.report import MaterialType, PriceReport
from app.services.price_history import build_history

logger = logging.getLogger(__name__)

BASELINE_MODEL_NAME = "moving_average"


class ForecastModel(Protocol):
    """Minimal interface every forecast model must satisfy (Step 11, section 27).

    ``fit`` sees ONLY the chronological training prefix (oldest -> newest,
    ``price_per_kg`` daily averages ``<= T``). ``predict`` returns one price
    per future day. Fully deterministic, no hidden data access.
    """

    name: str

    def fit(self, prices: List[float]) -> float:
        """Fit on training prices; return the single baseline level."""
        ...  # pragma: no cover

    def predict(self, level: float, n_days: int) -> List[float]:
        """Expand a fitted level into ``n_days`` daily predictions."""
        ...  # pragma: no cover


class MovingAverageBaseline:
    """Deterministic recent-moving-average baseline (no ML dependencies).

    ``fit`` returns the mean of the most recent ``window`` observed daily
    averages; ``predict`` repeats that flat level for each future day (a
    moving-average baseline has no trend component by design).
    """

    name = BASELINE_MODEL_NAME

    def __init__(self, window: Optional[int] = None):
        self.window = int(window if window is not None else settings.FORECAST_BASELINE_WINDOW)

    def fit(self, prices: List[float]) -> float:
        recent = list(prices[-self.window :]) if self.window > 0 else list(prices)
        if not recent:
            raise ValueError("cannot fit moving average on empty history")
        return float(statistics.fmean(recent))

    def predict(self, level: float, n_days: int) -> List[float]:
        return [float(level) for _ in range(int(n_days))]


def _resolve_scope_label(
    city: Optional[str],
    neighborhood: Optional[str],
) -> str:
    """Explicit scope for a forecast request (no silent fallback).

    Same rule as the historical layer: neighborhood value present ->
    ``"neighborhood"``, else city value present -> ``"city"``, else
    ``"country"`` (whole market). Used only for non-ready results where no
    trend object exists to report its scope.
    """
    if normalize_place_part(neighborhood) is not None:
        return "neighborhood"
    if normalize_place_part(city) is not None:
        return "city"
    return "country"


def _empty_result(
    *,
    material: MaterialType,
    currency: str,
    country: Optional[str],
    city: Optional[str],
    neighborhood: Optional[str],
    scope: str,
    status: str,
) -> ForecastResult:
    """Non-ready forecast: explicit status with ``points=[]`` (never zeros)."""
    return ForecastResult(
        material_type=material,
        currency=currency,
        country=country,
        city=city,
        neighborhood=neighborhood,
        scope=scope,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        source="reports",
        model=BASELINE_MODEL_NAME,
        historical_start=None,
        historical_end=None,
        forecast_start=None,
        forecast_end=None,
        horizon_days=0,
        training_report_count=0,
        training_points=0,
        validation_mae=None,
        validation_points=0,
        points=[],
    )


def _material_or_none(value: object) -> Optional[MaterialType]:
    try:
        return value if isinstance(value, MaterialType) else MaterialType(str(value).strip().lower())
    except (ValueError, AttributeError):
        return None


def build_forecast(
    material: MaterialType | str,
    reports: List[PriceReport],
    currency: str = UNKNOWN_CURRENCY,
    country: Optional[str] = None,
    city: Optional[str] = None,
    neighborhood: Optional[str] = None,
    horizon_days: Optional[int] = None,
    end_date: date | datetime | str | None = None,
    model: Optional[ForecastModel] = None,
) -> ForecastResult:
    """Build a baseline forecast from an explicit report list.

    Pure function (no repository access) so tests can inject exact
    populations. Trust + market + scope + range filtering is delegated to
    ``price_history.build_history``; this function adds only the training
    window, minimum-history policy, baseline fit, chronological validation,
    and horizon expansion -- all on data ``<= T`` (the forecast origin).
    """
    request_currency = normalize_currency(currency)
    request_country = normalize_place_part(country)
    request_city = normalize_place_part(city)
    request_neighborhood = normalize_place_part(neighborhood)

    material_enum = _material_or_none(material)
    if material_enum is None:
        logger.warning("Forecast rejected: unknown material %r", material)
        return _empty_result(
            material=MaterialType.OTHER,
            currency=request_currency,
            country=request_country,
            city=request_city,
            neighborhood=request_neighborhood,
            scope=_resolve_scope_label(request_city, request_neighborhood),
            status="invalid_request",
        )

    # Horizon policy: configured default, validated as
    # 1 <= horizon <= MAX_FORECAST_HORIZON_DAYS (modest by design).
    horizon = settings.FORECAST_HORIZON_DAYS if horizon_days is None else horizon_days
    try:
        horizon = int(horizon)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        logger.warning("Forecast rejected: invalid horizon %r", horizon_days)
        return _empty_result(
            material=material_enum,
            currency=request_currency,
            country=request_country,
            city=request_city,
            neighborhood=request_neighborhood,
            scope=_resolve_scope_label(request_city, request_neighborhood),
            status="invalid_request",
        )
    if horizon < 1 or horizon > int(settings.MAX_FORECAST_HORIZON_DAYS):
        logger.warning(
            "Forecast rejected: horizon %r outside [1, %s]",
            horizon_days,
            settings.MAX_FORECAST_HORIZON_DAYS,
        )
        return _empty_result(
            material=material_enum,
            currency=request_currency,
            country=request_country,
            city=request_city,
            neighborhood=request_neighborhood,
            scope=_resolve_scope_label(request_city, request_neighborhood),
            status="invalid_request",
        )

    # Historical series: ACCEPTED-only, same market, exact scope, capped at
    # the forecast origin (end_date). Future observations never enter.
    try:
        trend = build_history(
            material_enum,
            reports,
            currency=request_currency,
            country=request_country,
            city=request_city,
            neighborhood=request_neighborhood,
            end_date=end_date,
        )
    except ValueError:
        logger.warning("Forecast rejected: unknown material %r", material, exc_info=True)
        return _empty_result(
            material=MaterialType.OTHER,
            currency=request_currency,
            country=request_country,
            city=request_city,
            neighborhood=request_neighborhood,
            scope=_resolve_scope_label(request_city, request_neighborhood),
            status="invalid_request",
        )

    if not trend.points:
        return _empty_result(
            material=material_enum,
            currency=trend.currency,
            country=trend.country,
            city=trend.city,
            neighborhood=trend.neighborhood,
            scope=trend.scope,
            status="no_history",
        )

    # Explicit training window ending at the origin (latest observation).
    # Stale-for-estimate reports inside the window remain valid training data.
    origin = max(p.date for p in trend.points)
    window_days = max(int(settings.FORECAST_TRAINING_WINDOW_DAYS), 1)
    cutoff = origin - timedelta(days=window_days - 1)
    windowed = [p for p in trend.points if p.date >= cutoff]
    if not windowed:
        return _empty_result(
            material=material_enum,
            currency=trend.currency,
            country=trend.country,
            city=trend.city,
            neighborhood=trend.neighborhood,
            scope=trend.scope,
            status="no_history",
        )

    # Minimum-history policy: enough daily buckets spanning enough calendar
    # days. Passing only permits an attempt -- it never claims accuracy.
    earliest = min(p.date for p in windowed)
    span_days = (origin - earliest).days + 1
    if len(windowed) < int(settings.FORECAST_MIN_POINTS) or span_days < int(
        settings.FORECAST_MIN_DAYS
    ):
        logger.info(
            "Forecast insufficient_history: material='%s' market=(currency='%s', country='%s') "
            "scope='%s' has %d daily buckets over %d days (need %d buckets over %d days)",
            material_enum.value,
            trend.currency,
            trend.country,
            trend.scope,
            len(windowed),
            span_days,
            settings.FORECAST_MIN_POINTS,
            settings.FORECAST_MIN_DAYS,
        )
        return _empty_result(
            material=material_enum,
            currency=trend.currency,
            country=trend.country,
            city=trend.city,
            neighborhood=trend.neighborhood,
            scope=trend.scope,
            status="insufficient_history",
        )

    # Baseline fit on training data only (last N observed daily averages).
    baseline = model or MovingAverageBaseline()
    ordered = sorted(windowed, key=lambda p: p.date)
    train_prices = [float(p.average_price) for p in ordered]
    level = float(baseline.fit(train_prices))
    predicted = round(level, 2)

    # Chronological validation: fit the SAME baseline on the train prefix
    # only, measure MAE on the later holdout. Diagnostic, never confidence.
    validation_mae: Optional[float] = None
    validation_points = 0
    need = int(settings.FORECAST_MIN_POINTS) + int(settings.FORECAST_VALIDATION_POINTS)
    if len(ordered) >= need and int(settings.FORECAST_VALIDATION_POINTS) > 0:
        holdout_n = int(settings.FORECAST_VALIDATION_POINTS)
        prefix = train_prices[:-holdout_n]
        holdout = ordered[-holdout_n:]
        prefix_level = float(baseline.fit(prefix))
        errors = [abs(float(p.average_price) - prefix_level) for p in holdout]
        validation_mae = round(float(statistics.fmean(errors)), 2)
        validation_points = holdout_n

    forecast_start = origin + timedelta(days=1)
    forecast_end = origin + timedelta(days=horizon)
    levels = baseline.predict(level, horizon)
    points = [
        ForecastPoint(
            date=forecast_start + timedelta(days=i),
            predicted_price=round(float(v), 2),
        )
        for i, v in enumerate(levels)
    ]
    # Determinism guard: every baseline point equals the fitted level.
    assert all(p.predicted_price == predicted for p in points)

    result = ForecastResult(
        material_type=material_enum,
        currency=trend.currency,
        country=trend.country,
        city=trend.city,
        neighborhood=trend.neighborhood,
        scope=trend.scope,
        status="ready",
        source="reports",
        model=getattr(baseline, "name", BASELINE_MODEL_NAME),
        historical_start=earliest,
        historical_end=origin,
        forecast_start=forecast_start,
        forecast_end=forecast_end,
        horizon_days=horizon,
        training_report_count=int(sum(p.report_count for p in windowed)),
        training_points=len(windowed),
        validation_mae=validation_mae,
        validation_points=validation_points,
        points=points,
    )
    logger.info(
        "Forecast ready: material='%s' market=(currency='%s', country='%s') scope='%s' "
        "model='%s' history=[%s, %s] (%d reports in %d daily buckets) "
        "-> %d days from %s at %.2f %s/kg%s",
        material_enum.value,
        trend.currency,
        trend.country,
        trend.scope,
        result.model,
        earliest,
        origin,
        result.training_report_count,
        result.training_points,
        horizon,
        forecast_start,
        predicted,
        trend.currency,
        f" (validation_mae={validation_mae} over {validation_points}d)" if validation_mae is not None else "",
    )
    return result


class PriceForecastService:
    """Repository-backed baseline forecasts (Step 11)."""

    def __init__(self, repo: Optional[ReportRepository] = None):
        self.repo = repo or report_repo

    def get_forecast(
        self,
        material: Union[MaterialType, str],
        currency: str = UNKNOWN_CURRENCY,
        country: Optional[str] = None,
        city: Optional[str] = None,
        neighborhood: Optional[str] = None,
        horizon_days: Optional[int] = None,
        end_date: date | datetime | str | None = None,
        reports: Optional[List[PriceReport]] = None,
    ) -> ForecastResult:
        """Return the baseline forecast for the requested market/scope.

        Defaults to the trusted store (ACCEPTED-only via
        ``repo.trusted_reports()``); callers may inject an explicit list
        (tests, backfills). Trust is re-applied inside ``build_history`` so
        unfiltered lists can never leak PENDING/REJECTED data. The forecast
        origin is the latest eligible historical observation -- never a seed
        price and never the current estimator output.
        """
        if reports is None:
            reports = self.repo.trusted_reports()
        return build_forecast(
            material,
            reports,
            currency=currency,
            country=country,
            city=city,
            neighborhood=neighborhood,
            horizon_days=horizon_days,
            end_date=end_date,
        )


price_forecast_service = PriceForecastService()
