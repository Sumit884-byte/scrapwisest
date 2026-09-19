"""
ml_classifier_model.py

Loads the trained EfficientNetB0 waste-classifier exported from the
ScrapSense open-set + active-learning notebook, and exposes a load/predict
interface -- mirrors the load()/score() pattern already used by
ml_anomaly_model.py for consistency.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

try:
    import numpy as np
    from tensorflow import keras
    from tensorflow.keras.applications.efficientnet import preprocess_input
except ImportError:  # MVP API deploy does not require TensorFlow
    np = None
    keras = None
    preprocess_input = None

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent
_PACKAGE_MODEL_DIR = _BASE_DIR / "models" / "classifier"
_CWD_MODEL_DIR = Path("models/classifier")

MODEL_DIR = _PACKAGE_MODEL_DIR if _PACKAGE_MODEL_DIR.exists() else _CWD_MODEL_DIR
MODEL_PATH = MODEL_DIR / "scrapsense_model.keras"
CONFIG_PATH = MODEL_DIR / "config.json"

IMG_SIZE_DEFAULT = (224, 224)


@dataclass
class ClassifierBundle:
    model: object
    class_names: list
    threshold: float
    img_size: tuple


def load() -> ClassifierBundle | None:
    """Load the trained model + its config. Returns None if not exported yet."""
    if keras is None:
        logger.info("TensorFlow is not installed — CNN classifier disabled.")
        return None
    if not MODEL_PATH.exists() or not CONFIG_PATH.exists():
        logger.info("Classifier model or config missing at %s / %s", MODEL_PATH, CONFIG_PATH)
        return None

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    model = keras.models.load_model(MODEL_PATH)
    bundle = ClassifierBundle(
        model=model,
        class_names=config["class_names"],
        threshold=config["open_set_threshold"],
        img_size=tuple(config.get("img_size", IMG_SIZE_DEFAULT)),
    )
    logger.info(
        "Loaded CNN classifier bundle: classes=%s threshold=%.2f img_size=%s",
        bundle.class_names,
        bundle.threshold,
        bundle.img_size,
    )
    return bundle


def predict(bundle: ClassifierBundle, image_path: str) -> tuple[str, float]:
    """
    Run the CNN + open-set threshold on a single image.
    Returns (label, confidence). label == "unknown" if below threshold.
    """
    logger.info("Running CNN prediction on image: %s", image_path)
    img = keras.utils.load_img(image_path, target_size=bundle.img_size)
    arr = keras.utils.img_to_array(img)
    arr = preprocess_input(arr)
    arr = np.expand_dims(arr, axis=0)

    probs = bundle.model.predict(arr, verbose=0)[0]
    top_idx = int(np.argmax(probs))
    confidence = float(np.max(probs))

    if confidence < bundle.threshold:
        logger.info(
            "CNN predicted '%s' with confidence %.3f (< threshold %.2f) -> marked as 'unknown'",
            bundle.class_names[top_idx],
            confidence,
            bundle.threshold,
        )
        return "unknown", confidence
    
    logger.info(
        "CNN predicted '%s' with confidence %.3f (>= threshold %.2f)",
        bundle.class_names[top_idx],
        confidence,
        bundle.threshold,
    )
    return bundle.class_names[top_idx], confidence
