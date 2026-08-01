"""
ml_classifier_model.py

Loads the trained EfficientNetB0 waste-classifier exported from the
ScrapSense open-set + active-learning notebook, and exposes a load/predict
interface -- mirrors the load()/score() pattern already used by
ml_anomaly_model.py for consistency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from tensorflow import keras
from tensorflow.keras.applications.efficientnet import preprocess_input

MODEL_DIR = Path("models/classifier")
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
    if not MODEL_PATH.exists() or not CONFIG_PATH.exists():
        return None

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    model = keras.models.load_model(MODEL_PATH)
    return ClassifierBundle(
        model=model,
        class_names=config["class_names"],
        threshold=config["open_set_threshold"],
        img_size=tuple(config.get("img_size", IMG_SIZE_DEFAULT)),
    )


def predict(bundle: ClassifierBundle, image_path: str) -> tuple[str, float]:
    """
    Run the CNN + open-set threshold on a single image.
    Returns (label, confidence). label == "unknown" if below threshold.
    """
    img = keras.utils.load_img(image_path, target_size=bundle.img_size)
    arr = keras.utils.img_to_array(img)
    arr = preprocess_input(arr)
    arr = np.expand_dims(arr, axis=0)

    probs = bundle.model.predict(arr, verbose=0)[0]
    top_idx = int(np.argmax(probs))
    confidence = float(np.max(probs))

    if confidence < bundle.threshold:
        return "unknown", confidence
    return bundle.class_names[top_idx], confidence