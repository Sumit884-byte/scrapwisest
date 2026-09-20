"""
Image processing and classification service for ScrapSense.
Handles image file uploads, format/size validation, and CNN classification inference.
"""

from __future__ import annotations

import io
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.exceptions import InvalidImageError

try:
    import numpy as np
    from tensorflow import keras
    from tensorflow.keras.applications.efficientnet import preprocess_input
except ImportError:
    np = None
    keras = None
    preprocess_input = None

logger = logging.getLogger(__name__)


@dataclass
class ClassifierBundle:
    model: object
    class_names: list
    threshold: float
    img_size: tuple


def load_classifier_bundle() -> Optional[ClassifierBundle]:
    """Load the trained EfficientNetB0 CNN model + config if available."""
    if keras is None:
        logger.info("TensorFlow is not installed — CNN classifier disabled.")
        return None
    if not settings.CLASSIFIER_MODEL_PATH.exists() or not settings.CLASSIFIER_CONFIG_PATH.exists():
        logger.info(
            "Classifier model or config missing at %s / %s",
            settings.CLASSIFIER_MODEL_PATH,
            settings.CLASSIFIER_CONFIG_PATH,
        )
        return None

    try:
        with open(settings.CLASSIFIER_CONFIG_PATH) as f:
            config = json.load(f)

        model = keras.models.load_model(settings.CLASSIFIER_MODEL_PATH)
        bundle = ClassifierBundle(
            model=model,
            class_names=config["class_names"],
            threshold=config["open_set_threshold"],
            img_size=tuple(config.get("img_size", (224, 224))),
        )
        logger.info(
            "Loaded CNN classifier bundle: classes=%s threshold=%.2f img_size=%s",
            bundle.class_names,
            bundle.threshold,
            bundle.img_size,
        )
        return bundle
    except Exception:
        logger.exception("Failed to load CNN classifier bundle")
        return None


def predict_material(bundle: ClassifierBundle, image_path: str) -> Tuple[str, float]:
    """Run CNN inference with open-set threshold on a single image."""
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


class ImageService:
    def __init__(self):
        self._bundle: Optional[ClassifierBundle] = load_classifier_bundle()
        self.upload_dir = settings.UPLOAD_DIR
        self.max_bytes = settings.MAX_IMAGE_BYTES
        self.allowed_suffixes = settings.ALLOWED_IMAGE_SUFFIXES

    async def save_image(self, image: UploadFile) -> str:
        """Validates and saves an uploaded image file to disk."""
        logger.info("Saving uploaded image: filename='%s'", image.filename)
        data = await image.read()
        if not data:
            logger.warning("Upload failed: empty image file")
            raise HTTPException(status_code=400, detail="Empty image upload.")
        if len(data) > self.max_bytes:
            logger.warning("Upload failed: size %d bytes exceeds 8MB limit", len(data))
            raise HTTPException(status_code=400, detail="Image too large (max 8MB).")

        try:
            with Image.open(io.BytesIO(data)) as img:
                img.verify()
        except UnidentifiedImageError:
            logger.warning("Upload failed: unidentified image format")
            raise HTTPException(status_code=400, detail="File is not a valid image.")

        suffix = Path(image.filename or "").suffix.lower()
        if suffix not in self.allowed_suffixes:
            suffix = ".jpg"

        dest = self.upload_dir / f"{uuid.uuid4().hex}{suffix}"
        dest.write_bytes(data)
        logger.info("Saved image (%d bytes) to %s", len(data), dest)
        return str(dest)

    def classify_image(self, image_path: str) -> dict:
        """Classify waste material from a saved image file."""
        logger.info("Starting image classification pipeline for: %s", image_path)
        if self._bundle is None:
            self._bundle = load_classifier_bundle()

        if self._bundle is None:
            logger.warning("CNN classifier is not available. Asking the picker instead.")
            return {"error": "classifier_unavailable"}

        try:
            label, confidence = predict_material(self._bundle, image_path)
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
        except Exception:
            logger.exception("Error running prediction in ImageService")
            return {"error": "classification_failed"}

    def friendly_name(self, material: str) -> str:
        en, ur = settings.FRIENDLY_MATERIAL_NAMES.get(
            material, (material.replace("_", " ").title(), "")
        )
        return f"{en} ({ur})" if ur else en

    def format_classification_reply(self, result: dict) -> str:
        """Static, no-LLM reply for the photo-only path."""
        if "error" in result:
            return "Sorry, I couldn't read that photo right now. What material is it?"
        return f"That looks like: {self.friendly_name(result['material_type'])}."


image_service = ImageService()

# Standalone function exports for backwards compatibility
def classify_image(image_path: str) -> dict:
    return image_service.classify_image(image_path)


def friendly_name(material: str) -> str:
    return image_service.friendly_name(material)


def format_classification_reply(result: dict) -> str:
    return image_service.format_classification_reply(result)
