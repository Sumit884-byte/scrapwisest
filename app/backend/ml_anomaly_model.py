"""
ml_anomaly_model.py

A third, optional detection signal for the anomaly agent: an Isolation
Forest trained on pooled report features. Unlike the deterministic and LLM
modes, this one is USELESS until there's real data -- see MIN_REPORTS_TO_TRAIN.

The trick that makes this usable earlier than you'd expect: instead of
training a separate model per material (which would each need their own
50+ reports), we normalize price as a ratio to that material's own recent
median. That lets one small model pool data across ALL materials together,
so you hit the training threshold much sooner.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest

MIN_REPORTS_TO_TRAIN = 50  # below this, an Isolation Forest is just noise
MODEL_PATH = Path("models/isolation_forest.pkl")

# Tuned on 320 synthetic reports (see anomaly_model_analysis.ipynb):
# precision 1.00 / recall 0.89 / f1 0.94 on the anomaly class.
# Re-tune once real labelled reports replace the synthetic set.
CONTAMINATION = 0.05  # ~5% of historical reports assumed bad
N_ESTIMATORS = 200
MAX_SAMPLES = 0.8


def _features(price_per_kg: float, quantity_kg: float, material_median: float) -> list[float]:
    """price_ratio lets us pool across materials. log1p on quantity keeps
    a few huge outlier submissions from dominating the split geometry."""
    price_ratio = price_per_kg / material_median if material_median else 1.0
    return [price_ratio, np.log1p(quantity_kg)]


def train(reports: list[dict]) -> IsolationForest | None:
    """
    reports: list of dicts with keys price_paid_pkr_per_kg, quantity_kg,
    material_median (that material's recent median at the time of the report).

    Returns None if there isn't enough data yet -- callers should fall back
    to skipping the ML check in that case, same pattern as the deterministic
    check's 'not enough history' fallback.
    """
    if len(reports) < MIN_REPORTS_TO_TRAIN:
        return None

    X = np.array(
        [
            _features(r["price_paid_pkr_per_kg"], r["quantity_kg"], r["material_median"])
            for r in reports
        ]
    )
    model = IsolationForest(
        contamination=CONTAMINATION,
        n_estimators=N_ESTIMATORS,
        max_samples=MAX_SAMPLES,
        random_state=42,
    )
    model.fit(X)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    return model


def load() -> IsolationForest | None:
    if not MODEL_PATH.exists():
        return None
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def score(
    model: IsolationForest, price_per_kg: float, quantity_kg: float, material_median: float
) -> tuple[bool, float]:
    """Returns (is_anomalous, raw_score). More negative raw_score = more
    anomalous, per sklearn's convention."""
    X = np.array([_features(price_per_kg, quantity_kg, material_median)])
    prediction = model.predict(X)[0]  # -1 = anomaly, 1 = normal
    raw_score = model.score_samples(X)[0]
    return bool(prediction == -1), float(raw_score)