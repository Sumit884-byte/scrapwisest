"""Service package with lazy exports.

Submodules form an import cycle through this package root
(repositories <-> services), so importing them eagerly here breaks any
entrypoint that reaches the repositories first (e.g. demo-data scripts).
Attribute access imports the defining submodule on demand instead.
"""

from __future__ import annotations

__all__ = [
    "PriceEstimatorService",
    "price_estimator_service",
    "estimate",
    "estimate_price",
    "SEED_PRICES",
    "AnomalyDetectorService",
    "anomaly_detector_service",
    "train_ml_model",
    "load_ml_model",
    "ml_score",
    "retrain",
    "ImageService",
    "image_service",
    "classify_image",
    "friendly_name",
    "format_classification_reply",
    "ClassifierBundle",
    "load_classifier_bundle",
    "predict_material",
]


def __getattr__(name: str):
    if name in {
        "PriceEstimatorService",
        "price_estimator_service",
        "estimate",
        "estimate_price",
        "SEED_PRICES",
    }:
        from app.services import price_estimator as module

        return getattr(module, name)
    if name in {
        "AnomalyDetectorService",
        "anomaly_detector_service",
        "train_ml_model",
        "load_ml_model",
        "ml_score",
        "retrain",
    }:
        from app.services import anomaly_detector as module

        return getattr(module, name)
    if name in {
        "ImageService",
        "image_service",
        "classify_image",
        "friendly_name",
        "format_classification_reply",
        "ClassifierBundle",
        "load_classifier_bundle",
        "predict_material",
    }:
        from app.services import image_service as module

        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
