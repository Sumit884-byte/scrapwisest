"""
Anomaly Detection service for Scrapwisest.
Implements the multi-tiered anomaly detection logic:
  1. Deterministic bounds check against regional median
  2. Machine Learning scoring using Isolation Forest
  3. Model retraining functionality from trusted reports
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
from app.schemas.report import AnomalyVerdict, PriceReport

logger = logging.getLogger(__name__)


def _features(price_per_kg: float, quantity_kg: float, material_median: float) -> list[float]:
    """Price ratio normalizes across materials; log1p dampens large quantity outliers."""
    price_ratio = price_per_kg / material_median if material_median else 1.0
    return [price_ratio, float(np.log1p(quantity_kg))]


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
        trusted = self.repo.trusted_reports()
        prices_by_material: Dict = defaultdict(list)
        for r in trusted:
            prices_by_material[r.material_type].append(r.price_per_kg)
        medians = {m: statistics.median(p) for m, p in prices_by_material.items()}
        records = [
            {
                "price_per_kg": r.price_per_kg,
                "quantity_kg": r.quantity_kg,
                "material_median": medians.get(r.material_type, r.price_per_kg),
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
