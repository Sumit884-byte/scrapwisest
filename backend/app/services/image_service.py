"""
Image processing and classification service for Scrapwisest.
Handles image file uploads, format/size validation, and CNN classification inference.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
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


CNN_LABEL_MAP = {
    "cardboard": "cardboard",
    "glass": "glass",
    "paper": "mixed_paper",
}

AMBIGUOUS_CNN_LABELS = {"plastic", "metal"}
VISION_LABELS = {"cardboard", "glass", "metal", "paper", "plastic", "trash", "unknown"}
_VISION_PROMPT = (
    "You grade scrap photos for a waste-picker app. Look at the image and "
    "return ONLY JSON: {\"label\": \"<one>\", \"confidence\": <0-1>}. "
    "label must be one of: plastic, metal, glass, paper, cardboard, trash, unknown. "
    "Use plastic for bottles, containers, toys, and other plastic items. "
    "Use metal for cans, steel, or aluminum. Use trash for mixed junk that is "
    "not a recyclable scrap pile. Use unknown if you cannot tell."
)


def map_classifier_label(label: str) -> Optional[str]:
    """Map CNN labels to supported market materials without guessing subtypes."""
    return CNN_LABEL_MAP.get(label.strip().lower())


def _strip_json_wrapper(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    return cleaned


def parse_vision_classification(raw: str) -> Optional[dict]:
    """Parse a vision model JSON payload into a classifier-style result."""
    try:
        payload = json.loads(_strip_json_wrapper(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    label = str(payload.get("label", "")).strip().lower()
    if label not in VISION_LABELS:
        return None
    try:
        confidence = float(payload.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    return classification_from_label(label, confidence, source="vision")


def classification_from_label(label: str, confidence: float, source: str) -> dict:
    if label == "unknown":
        return {"error": "low_confidence", "confidence": confidence, "source": source}

    normalized = map_classifier_label(label)
    if normalized is None:
        if label in AMBIGUOUS_CNN_LABELS:
            return {
                "error": "ambiguous_material",
                "category": label,
                "confidence": confidence,
                "source": source,
            }
        return {
            "error": "unsupported_material",
            "category": label,
            "confidence": confidence,
            "source": source,
        }
    return {"material_type": normalized, "confidence": confidence, "source": source}


def _vision_configured() -> bool:
    return bool(settings.GROQ_API_KEY.strip())


def _image_data_url(image_path: str) -> str:
    with Image.open(image_path) as img:
        frame = img.convert("RGB")
        frame.thumbnail((1280, 1280))
        buf = io.BytesIO()
        frame.save(buf, format="JPEG", quality=85)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def classify_with_vision(image_path: str) -> dict:
    """Grade a photo with Groq vision when the local CNN is unavailable."""
    if not _vision_configured():
        return {"error": "classifier_unavailable"}
    try:
        from groq import Groq

        client = Groq(api_key=settings.GROQ_API_KEY.strip())
        models = []
        for mid in (
            settings.GROQ_VISION_MODEL,
            "qwen/qwen3.8-27b",
            "meta-llama/llama-4-scout-17b-16e-instruct",
        ):
            if mid and mid not in models:
                models.append(mid)
        last_error: Exception | None = None
        completion = None
        for model in models:
            try:
                completion = client.chat.completions.create(
                    model=model,
                    temperature=0,
                    max_completion_tokens=128,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": _VISION_PROMPT},
                                {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                            ],
                        }
                    ],
                )
                logger.info("Vision classification used model %s", model)
                break
            except Exception as exc:
                last_error = exc
                logger.warning("Vision model %s failed: %s", model, exc)
        if completion is None:
            raise last_error or RuntimeError("No vision model available")
        raw = (completion.choices[0].message.content or "").strip()
        parsed = parse_vision_classification(raw)
        if parsed is None:
            logger.warning("Vision classifier returned unusable payload")
            return {"error": "classification_failed", "source": "vision"}
        logger.info("Classification completed via vision model: %s", parsed)
        return parsed
    except Exception:
        logger.exception("Vision classification failed")
        return {"error": "classification_failed", "source": "vision"}


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
            logger.warning("CNN classifier is not available. Using vision fallback.")
            return classify_with_vision(image_path)

        try:
            label, confidence = predict_material(self._bundle, image_path)
            result = classification_from_label(label, confidence, source="cnn")
            if result.get("error") in {"low_confidence", "unsupported_material"}:
                logger.info("CNN was inconclusive (%s). Trying vision fallback.", result["error"])
                vision = classify_with_vision(image_path)
                if "error" not in vision or vision.get("error") == "ambiguous_material":
                    return vision
            if "error" not in result:
                logger.info("Classification completed via CNN model: %s", result)
            return result
        except Exception:
            logger.exception("Error running prediction in ImageService")
            return classify_with_vision(image_path)

    def cleanup_image(self, image_path: str) -> None:
        """Remove a temporary upload after classification has finished."""
        try:
            path = Path(image_path)
            if path.exists():
                path.unlink()
                logger.info("Removed temporary image upload: %s", path)
        except OSError:
            # Cleanup must never turn a successful chat request into an error.
            logger.warning("Could not remove temporary image upload: %s", image_path, exc_info=True)

    def friendly_name(self, material: str) -> str:
        names = settings.FRIENDLY_MATERIAL_NAMES.get(
            material, (material.replace("_", " ").title(), "", "")
        )
        en = names[0]
        ur = names[1] if len(names) > 1 else ""
        return f"{en} ({ur})" if ur else en

    def format_classification_reply(self, result: dict, language: str = "") -> str:
        """Static, no-LLM reply for the photo-only path."""
        lang = (language or "").strip().lower()
        name = self.friendly_name(result.get("material_type", "")) if "material_type" in result else ""
        if result.get("error") == "ambiguous_material":
            category = result.get("category", "material")
            if category == "plastic":
                if lang == "hi":
                    return "यह प्लास्टिक लगता है। PET है या HDPE?"
                if lang == "hi-latn":
                    return "Yeh plastic lag raha hai. PET hai ya HDPE?"
                if lang == "ur":
                    return "یہ پلاسٹک لگ رہا ہے۔ PET ہے یا HDPE؟"
                if lang == "ur-latn":
                    return "Yeh plastic lag raha hai. PET hai ya HDPE?"
                if lang in {"te", "te-latn"}:
                    return "Idi plastic la undi. PET aa HDPE aa?"
                return "This looks like plastic. Is it PET or HDPE?"
            if category == "metal":
                if lang == "hi":
                    return "यह धातु लगता है। एल्युमिनियम है या स्टील?"
                if lang == "hi-latn":
                    return "Yeh metal lag raha hai. Aluminum hai ya steel?"
                if lang == "ur":
                    return "یہ دھات لگ رہی ہے۔ ایلومینیم ہے یا سٹیل؟"
                if lang == "ur-latn":
                    return "Yeh dhat lag rahi hai. Aluminum hai ya steel?"
                if lang in {"te", "te-latn"}:
                    return "Idi metal la undi. Aluminum aa steel aa?"
                return "This looks like metal. Is it aluminum or steel?"
        if "error" in result:
            if lang == "hi":
                return "फोटो साफ नहीं पढ़ सका। यह कौन सा माल है?"
            if lang == "hi-latn":
                return "Photo saaf nahi padh paya. Yeh kaun sa maal hai?"
            if lang == "ur":
                return "تصویر صاف نہیں پڑھی۔ یہ کون سا مال ہے؟"
            if lang == "ur-latn":
                return "Photo saaf nahi parhi. Yeh konsa maal hai?"
            if lang in {"te", "te-latn"}:
                return "Photo clear ga chadhvale. Idi e material?"
            return "Sorry, I couldn't read that photo right now. What material is it?"
        if lang == "hi":
            return f"यह {name} लगता है।"
        if lang == "hi-latn":
            return f"Yeh {name} lag raha hai."
        if lang == "ur":
            return f"یہ {name} لگ رہا ہے۔"
        if lang == "ur-latn":
            return f"Yeh {name} lag raha hai."
        if lang in {"te", "te-latn"}:
            return f"Idi {name} la undi."
        return f"That looks like: {name}."


image_service = ImageService()

# Standalone function exports for backwards compatibility
def classify_image(image_path: str) -> dict:
    return image_service.classify_image(image_path)


def friendly_name(material: str) -> str:
    return image_service.friendly_name(material)


def format_classification_reply(result: dict, language: str = "") -> str:
    return image_service.format_classification_reply(result, language)
