"""
Anomaly Detection service for Scrapwisest.
Implements the multi-tiered anomaly detection logic:
  1. Deterministic bounds check against a market-scoped median
  2. Machine Learning scoring using Isolation Forest
  3. Model retraining functionality from trusted reports

Market/location scoping (Step 4):

  Every comparison first restricts to the appropriate anomaly population:
  same material + same market (``market_key(country, currency)``), then the
  tightest location scope with data: neighborhood -> city -> market.
  Location is a population/filtering boundary only -- city/neighborhood
  names are never encoded as ML numbers.

  Currency isolation is absolute: PKR reports never influence INR/USD
  decisions. Country is part of the market identity (``country + currency``
  via the canonical ``market_key()``), so two USD countries stay separate.
  City matching always includes the country (``same_city()``) and
  neighborhood matching always includes city + country
  (``same_neighborhood()``), so identical names in different cities never
  pool together.

  Unknown/missing markets (``currency="unknown"``, no country) form their
  own population and never join Pakistan/PKR -- the Step 2 legacy seed
  compatibility for the estimator is deliberately NOT carried into anomaly
  detection.

  The Isolation Forest itself stays a single market-agnostic model over
  ``[price_ratio, log1p(quantity)]`` where ``price_ratio`` is normalized
  against the report's own market median. Retraining groups medians by
  ``(material, market)`` so no mixed-market distribution is learned.
"""

from __future__ import annotations

import logging
import pickle
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import IsolationForest

from app.core.config import settings
from app.repositories.report_repository import ReportRepository, report_repo
from app.schemas.market import UNKNOWN_CURRENCY, market_key
from app.schemas.report import AnomalyVerdict, PriceReport
from app.services.location_resolver import (
    neighborhood_label,
    same_city,
    same_neighborhood,
)

logger = logging.getLogger(__name__)


def _features(price_per_kg: float, quantity_kg: float, material_median: float) -> list[float]:
    """Price ratio normalizes across materials; log1p dampens large quantity outliers."""
    price_ratio = price_per_kg / material_median if material_median else 1.0
    return [price_ratio, float(np.log1p(quantity_kg))]


def _material_value(report_or_material) -> str:
    """Canonical material identity shared with the estimator/population code."""
    mat = getattr(report_or_material, "material_type", report_or_material)
    value = mat.value if hasattr(mat, "value") else str(mat)
    return value.strip().lower()


def in_same_market(first: PriceReport, second: PriceReport) -> bool:
    """True only when both reports share the canonical market identity.

    Uses the single ``market_key(country, currency)`` implementation --
    currency alone is never the identity, and unknown markets
    (``("unknown", "")``) only match other unknown markets, never
    Pakistan/PKR.
    """
    return market_key(first.country, first.currency) == market_key(
        second.country, second.currency
    )


def in_same_city_scope(first: PriceReport, second: PriceReport) -> bool:
    """True only when city AND country match (never city name alone)."""
    return same_city(first.city, first.country, second.city, second.country)


def in_same_neighborhood_scope(first: PriceReport, second: PriceReport) -> bool:
    """True only when neighborhood AND city AND country all match."""
    return same_neighborhood(
        first.neighborhood,
        first.city,
        first.country,
        first.location,
        second.neighborhood,
        second.city,
        second.country,
        second.location,
    )


def _market_pool(report: PriceReport, candidates: List[PriceReport]) -> List[PriceReport]:
    """Same material + same market (country + currency), any location."""
    wanted = _material_value(report)
    return [
        r
        for r in candidates
        if _material_value(r) == wanted and in_same_market(report, r)
    ]


def comparable_reports(
    report: PriceReport,
    candidates: List[PriceReport],
) -> List[PriceReport]:
    """Historical population for ``report``: tightest scope with real data.

    Fallback chain (all within the SAME material + SAME market):

    1. neighborhood scope (same neighborhood + city + country),
    2. city scope (same city + country),
    3. market scope (whole country + currency market).

    Each tier uses only real reports -- nothing is fabricated. Callers still
    apply ``MIN_REPORTS_FOR_BASELINE`` to the result, so sparse scopes fall
    through to the existing safe "not enough history -- accepted" behavior
    instead of inventing a baseline. Never crosses an incompatible market
    and never claims a local baseline across cities.
    """
    market_reports = _market_pool(report, candidates)

    # Neighborhood tier only applies when this report has a neighborhood
    # identity; a city-only report skips straight to city scope so it still
    # participates correctly.
    if neighborhood_label(report.neighborhood, report.location) is not None:
        neighborhood_reports = [
            r for r in market_reports if in_same_neighborhood_scope(report, r)
        ]
        if neighborhood_reports:
            return neighborhood_reports
        # Else fall through to city/market -- sparse neighborhoods use the
        # wider real baseline instead of a fabricated one.

    city_reports = [r for r in market_reports if in_same_city_scope(report, r)]
    if city_reports:
        return city_reports

    return market_reports


def comparable_prices(
    report: PriceReport,
    candidates: List[PriceReport],
) -> List[float]:
    """Price/kg series for the anomaly population of ``report``."""
    return [r.price_per_kg for r in comparable_reports(report, candidates)]


def market_median_for(report: PriceReport, candidates: List[PriceReport]) -> float:
    """Median price/kg for the report's material + market (any location).

    Used as the ML-tier normalization baseline. Returns 0.0 when the market
    has no history so callers keep their existing safe behavior.
    """
    pool = _market_pool(report, candidates)
    if not pool:
        return 0.0
    return statistics.median([r.price_per_kg for r in pool])


def population_scope(report: PriceReport, candidates: List[PriceReport]) -> str:
    """Which fallback tier ``comparable_reports`` selected (for logs/prompts)."""
    market_reports = _market_pool(report, candidates)
    if not market_reports:
        return "empty"
    neighborhood_reports = [r for r in market_reports if in_same_neighborhood_scope(report, r)]
    if neighborhood_reports:
        return "neighborhood"
    city_reports = [r for r in market_reports if in_same_city_scope(report, r)]
    if city_reports:
        return "city"
    return "market"


def describe_market(report: PriceReport) -> str:
    """Human-readable market/location label for logs and the LLM judge."""
    currency = (report.currency or UNKNOWN_CURRENCY).strip() or UNKNOWN_CURRENCY
    bits = [str(report.country).strip() if report.country else "unknown country"]
    bits.append(currency.upper())
    if report.city:
        bits.append(str(report.city).strip())
    label = neighborhood_label(report.neighborhood, report.location)
    if label:
        bits.append(label)
    return " / ".join(b for b in bits if b)


def train_ml_model(
    reports: list[dict],
    model_path: Optional[Path] = None,
) -> Optional[IsolationForest]:
    """Train Isolation Forest on pooled report features."""
    target_path = model_path or settings.ISOLATION_FOREST_PATH
    if len(reports) < settings.MIN_REPORTS_TO_TRAIN_ML:
        logger.info(
            "Insufficient reports to train Isolation Forest (%d/%d required)",
            len(reports),
            settings.MIN_REPORTS_TO_TRAIN_ML,
        )
        return None

    logger.info("Training Isolation Forest on %d reports...", len(reports))
    X = np.array(
        [
            # NOTE (Step 1): training-record key renamed to the generic
            # "price_per_kg". Old "price_paid_pkr_per_kg" keys are still
            # accepted for backwards compatibility.
            _features(
                r.get("price_per_kg", r.get("price_paid_pkr_per_kg")),
                r["quantity_kg"],
                r["material_median"],
            )
            for r in reports
        ]
    )
    model = IsolationForest(
        contamination=settings.CONTAMINATION_FACTOR,
        n_estimators=200,
        max_samples=0.8,
        random_state=42,
    )
    model.fit(X)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "wb") as f:
        pickle.dump(model, f)
    logger.info("Isolation Forest successfully trained and saved to %s", target_path)
    return model


def load_ml_model(model_path: Optional[Path] = None) -> Optional[IsolationForest]:
    target_path = model_path or settings.ISOLATION_FOREST_PATH
    if not target_path.exists():
        logger.info("No Isolation Forest model found at %s", target_path)
        return None
    try:
        with open(target_path, "rb") as f:
            model = pickle.load(f)
            logger.info("Isolation Forest anomaly model loaded from %s", target_path)
            return model
    except Exception:
        logger.exception("Failed to load Isolation Forest from %s", target_path)
        return None


def ml_score(
    model: IsolationForest,
    price_per_kg: float,
    quantity_kg: float,
    material_median: float,
) -> Tuple[bool, float]:
    """Scores an observation with Isolation Forest. Returns (is_anomalous, raw_score)."""
    feat = _features(price_per_kg, quantity_kg, material_median)
    X = np.array([feat])
    prediction = model.predict(X)[0]  # -1 = anomaly, 1 = normal
    raw_score = float(model.score_samples(X)[0])
    is_anom = bool(prediction == -1)
    logger.info(
        "ML anomaly score calculated: features=%s, raw_score=%.4f, prediction=%s (is_anomalous=%s)",
        feat,
        raw_score,
        "anomaly (-1)" if is_anom else "normal (+1)",
        is_anom,
    )
    return is_anom, raw_score


class AnomalyDetectorService:
    def __init__(self, repo: Optional[ReportRepository] = None):
        self.repo = repo or report_repo
        self.ml_model = load_ml_model()

    def deterministic_check(
        self,
        report: PriceReport,
        recent_prices_per_kg: List[float],
    ) -> AnomalyVerdict:
        logger.info(
            "Deterministic check running for %s @ %.2f %s/kg (history count=%d)",
            report.material_type.value if hasattr(report.material_type, "value") else str(report.material_type),
            report.price_per_kg,
            report.currency,
            len(recent_prices_per_kg),
        )
        if len(recent_prices_per_kg) < settings.MIN_REPORTS_FOR_BASELINE:
            verdict = AnomalyVerdict(
                is_anomalous=False,
                reason="not enough regional history yet -- accepted by default",
                method="deterministic",
            )
            logger.info("Deterministic check result: %s", verdict)
            return verdict

        median = statistics.median(recent_prices_per_kg)
        price = report.price_per_kg

        if price < median * settings.LOW_RATIO:
            verdict = AnomalyVerdict(
                is_anomalous=True,
                reason=f"price/kg ({price:.0f}) is under half the recent median ({median:.0f})",
                method="deterministic",
            )
        elif price > median * settings.HIGH_RATIO:
            verdict = AnomalyVerdict(
                is_anomalous=True,
                reason=f"price/kg ({price:.0f}) is over double the recent median ({median:.0f})",
                method="deterministic",
            )
        else:
            verdict = AnomalyVerdict(
                is_anomalous=False,
                reason=f"within normal range of recent median ({median:.0f})",
                method="deterministic",
            )
        logger.info("Deterministic check result: %s", verdict)
        return verdict

    def ml_check(
        self,
        report: PriceReport,
        material_median: float,
    ) -> AnomalyVerdict:
        if self.ml_model is None:
            self.ml_model = load_ml_model()

        if self.ml_model is None:
            return AnomalyVerdict(
                is_anomalous=False,
                reason="ml model not available -- skipped",
                method="ml",
                confidence=0.5,
            )

        mat_name = report.material_type.value if hasattr(report.material_type, "value") else str(report.material_type)
        logger.info("ML check running for %s with median=%.2f", mat_name, material_median)
        is_anom, raw_score = ml_score(
            self.ml_model, report.price_per_kg, report.quantity_kg, material_median
        )
        verdict = AnomalyVerdict(
            is_anomalous=is_anom,
            reason=f"isolation forest flagged this price/quantity combination (score {raw_score:.3f})",
            method="ml",
            confidence=min(1.0, abs(raw_score) * 2),
        )
        logger.info("ML check result: %s", verdict)
        return verdict

    def retrain(self) -> bool:
        # Market-scoped medians: each report's price_ratio is normalized
        # against its own (material, market) median, so the single Isolation
        # Forest never learns a mixed-market distribution (Option B -- filter
        # populations, not categorical encodings and not N separate models).
        trusted = self.repo.trusted_reports()
        prices_by_market: Dict = defaultdict(list)
        for r in trusted:
            prices_by_market[(_material_value(r), market_key(r.country, r.currency))].append(
                r.price_per_kg
            )
        medians = {m: statistics.median(p) for m, p in prices_by_market.items()}
        records = [
            {
                "price_per_kg": r.price_per_kg,
                "quantity_kg": r.quantity_kg,
                "material_median": medians.get(
                    (_material_value(r), market_key(r.country, r.currency)),
                    r.price_per_kg,
                ),
            }
            for r in trusted
        ]
        model = train_ml_model(records)
        if model:
            self.ml_model = model
        return model is not None


anomaly_detector_service = AnomalyDetectorService()

def retrain() -> bool:
    return anomaly_detector_service.retrain()
