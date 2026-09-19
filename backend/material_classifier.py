"""
Classifier for ScrapSense (secondary helper — the core product is price).

Identifies material from a photo when a picker is unsure. Wraps the trained
CNN when it is present. No LLM on this path: Token Factory credits stay on
the chat/extraction/judge calls, and a failed photo just asks the picker.
"""

from __future__ import annotations

import logging

import ml_classifier_model

logger = logging.getLogger(__name__)

_bundle = ml_classifier_model.load()

DEFAULT_CLASSES = [
    "plastic_pet", "plastic_hdpe", "glass", "metal_aluminum",
    "metal_steel", "cardboard", "mixed_paper", "other",
]


def classify_image(image_path: str) -> dict:
    """Entry point the API calls: photo -> material classification."""
    global _bundle
    logger.info("Starting image classification pipeline for: %s", image_path)
    if _bundle is None:
        _bundle = ml_classifier_model.load()

    if _bundle is None:
        logger.warning("CNN classifier is not available. Asking the picker instead.")
        return {"error": "classifier_unavailable"}

    label, confidence = ml_classifier_model.predict(_bundle, image_path)

    if label == "unknown":
        logger.info("CNN was below the open-set threshold. Not guessing.")
        return {
            "error": "low_confidence",
            "confidence": confidence,
            "source": "cnn",
        }

    res = {"material_type": label, "confidence": confidence, "source": "cnn"}
    logger.info("Classification completed via CNN model: %s", res)
    return res
