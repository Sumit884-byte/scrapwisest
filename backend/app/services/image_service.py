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
from app.core.exceptions import InvalidImageError, QuotaExceededError
from app.core.llm_budget import reserve_llm

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
    "carton": "cardboard",
    "corrugated": "cardboard",
    "glass": "glass",
    "paper": "mixed_paper",
    "newspaper": "mixed_paper",
    "newsprint": "mixed_paper",
    "plastic_pet": "plastic_pet",
    "pet": "plastic_pet",
    "plastic_hdpe": "plastic_hdpe",
    "hdpe": "plastic_hdpe",
    "metal_aluminum": "metal_aluminum",
    "aluminum": "metal_aluminum",
    "aluminium": "metal_aluminum",
    "metal_steel": "metal_steel",
    "steel": "metal_steel",
    "iron": "metal_steel",
    "trash": "other",
    "mixed": "other",
    "other": "other",
}

AMBIGUOUS_CNN_LABELS = {"plastic", "metal"}
NOT_SCRAP_LABELS = {
    "not_scrap",
    "person",
    "people",
    "selfie",
    "face",
    "human",
    "portrait",
    "unrelated",
}
VISION_LABELS = {
    "cardboard",
    "glass",
    "metal",
    "metal_aluminum",
    "metal_steel",
    "paper",
    "plastic",
    "plastic_pet",
    "plastic_hdpe",
    "trash",
    "mixed",
    "other",
    "unknown",
    *NOT_SCRAP_LABELS,
    *CNN_LABEL_MAP.keys(),
}
_LABEL_ALIASES = {
    "pet plastic": "plastic_pet",
    "plastic bottle": "plastic_pet",
    "plastic bottles": "plastic_pet",
    "water bottle": "plastic_pet",
    "soda bottle": "plastic_pet",
    "soft drink bottle": "plastic_pet",
    "milk jug": "plastic_hdpe",
    "detergent bottle": "plastic_hdpe",
    "shampoo bottle": "plastic_hdpe",
    "soda can": "metal_aluminum",
    "soda cans": "metal_aluminum",
    "beer can": "metal_aluminum",
    "aluminium can": "metal_aluminum",
    "aluminum can": "metal_aluminum",
    "aluminum cans": "metal_aluminum",
    "tin can": "metal_steel",
    "scrap iron": "metal_steel",
    "rusted iron": "metal_steel",
    "rebar": "metal_steel",
    "newspaper": "paper",
    "newspapers": "paper",
    "cardboard box": "cardboard",
    "cardboard boxes": "cardboard",
    "glass bottle": "glass",
    "glass bottles": "glass",
}
_SUBTYPE_PARENT = {
    "plastic_pet": "plastic",
    "plastic_hdpe": "plastic",
    "metal_aluminum": "metal",
    "metal_steel": "metal",
}
# Loose household scrap, mid of typical bulk-density ranges (kg per m³).
# Used only to convert a visible-volume guess into kg — not a sale weight.
_BULK_DENSITY_KG_M3 = {
    "plastic_pet": 35,
    "plastic_hdpe": 40,
    "metal_aluminum": 65,
    "metal_steel": 280,
    "glass": 300,
    "cardboard": 65,
    "mixed_paper": 110,
    "paper": 110,
    "other": 80,
}

_VISION_PROMPT = (
    "You grade scrap photos for a waste-picker price app. "
    "Look only at the physical material that fills most of the frame. "
    "Return ONLY JSON: {\"label\": \"<one>\", \"confidence\": <0-1>, "
    "\"volume_liters\": <number>, \"volume_liters_low\": <number>, "
    "\"volume_liters_high\": <number>, \"estimated_kg\": <number>}. "
    "Allowed labels: plastic_pet, plastic_hdpe, metal_aluminum, metal_steel, "
    "glass, paper, cardboard, mixed, not_scrap, unknown. "
    "Rules: "
    "plastic_pet = clear or tinted drink bottles, thin crinkly bottles, PET bales. "
    "plastic_hdpe = opaque jugs (milk, oil, detergent), thicker matte plastic. "
    "metal_aluminum = drink cans, thin crushed cans, foil-like metal. "
    "metal_steel = heavy rusted iron, rebar, steel sheets, thick cans. "
    "glass = glass bottles or jars, even if empty or broken. "
    "paper = newspapers, books, loose paper. "
    "cardboard = corrugated cartons and packing boxes. "
    "mixed = several scrap types piled together with no clear majority. "
    "not_scrap = people, selfies, food, pets, screenshots, rooms, or anything that is not scrap. "
    "unknown = scrap-like but you cannot name the material. "
    "If a person is holding scrap, grade the scrap, not the person. "
    "Prefer a specific subtype over generic plastic/metal. "
    "If you must choose plastic or metal without a subtype, still use plastic_pet "
    "for drink bottles and metal_aluminum for drink cans. "
    "Volume is a photo estimate of the visible pile, never a recorded sale. "
    "volume_liters = typical bulk volume of scrap in frame (a few bottles ~2-8 L, "
    "one sack ~40-80 L, a trolley ~150-300 L, a bale ~400-800 L). "
    "volume_liters_low / volume_liters_high = a plausible range around that typical. "
    "estimated_kg = typical mass from count and size (empty PET/cans are light). "
    "If not_scrap, set all volume fields to 0."
)


def normalize_vision_label(raw_label: str) -> str:
    """Map model wording onto a canonical vision label."""
    text = (raw_label or "").strip().lower().replace("-", " ")
    text = re.sub(r"[^a-z0-9_ ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    compact = text.replace(" ", "_")
    mapped = CNN_LABEL_MAP.get(compact)
    if mapped in _SUBTYPE_PARENT:
        return mapped
    if mapped == "mixed_paper":
        return "paper"
    if mapped in {"cardboard", "glass", "other"}:
        return mapped
    if compact in VISION_LABELS:
        return compact
    if text in _LABEL_ALIASES:
        return _LABEL_ALIASES[text]
    for phrase, mapped in sorted(_LABEL_ALIASES.items(), key=lambda item: -len(item[0])):
        if phrase in text:
            return mapped
    if compact in CNN_LABEL_MAP:
        return compact
    return compact or "unknown"


def _not_scrap_reply(lang: str) -> str:
    """Polite refusal when the photo is not scrap material."""
    if lang == "hi":
        return "🙂 यह स्क्रैप नहीं लगता। कृपया असली scrap की साफ़ तस्वीर भेजें — सेल्फी या और तस्वीरें नहीं।"
    if lang == "hi-latn":
        return "🙂 Yeh scrap nahi lag raha. Please asli scrap ki saaf photo bhejein — selfie ya aur pictures nahi."
    if lang == "ur":
        return "🙂 یہ اسکریپ نہیں لگتی۔ براہ کرم اصل اسکریپ کی صاف تصویر بھیجیں — سیلفی یا غیر متعلقہ تصویر نہیں۔"
    if lang == "ur-latn":
        return "🙂 Yeh scrap nahi lag rahi. Please asli scrap ki saaf photo bhejein — selfie ya unrelated picture nahi."
    if lang in {"te", "te-latn"}:
        return "🙂 Idi scrap la ledu. Please asalu scrap photo pampandi — selfie leka inka photos kadu."
    return (
        "🙂 This does not look like scrap. Please send a clear photograph of "
        "the actual material you want priced — portraits and unrelated pictures "
        "cannot be graded."
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


def _finite_in_range(value, lo: float, hi: float) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number < lo or number > hi:
        return None
    return number


def average_volume_from_vision(payload: dict, material_type: str) -> dict:
    """Blend the model's volume range with a density-based kg estimate.

    Average liters = midpoint of low/high when both are usable, else
    ``volume_liters``. Average kg = mean of the model's ``estimated_kg``
    and liters × typical loose-scrap density. Returns only keys that
    could be inferred; never invents a sale.
    """
    liters = _finite_in_range(
        payload.get("volume_liters") or payload.get("estimated_volume_liters"),
        0.1,
        5000,
    )
    low = _finite_in_range(payload.get("volume_liters_low"), 0.1, 5000)
    high = _finite_in_range(payload.get("volume_liters_high"), 0.1, 5000)
    vision_kg = _finite_in_range(
        payload.get("estimated_kg") or payload.get("volume_kg") or payload.get("estimated_quantity_kg"),
        0.05,
        2000,
    )
    if low is not None and high is not None and high >= low:
        avg_liters = (low + high) / 2.0
    else:
        avg_liters = liters

    density = _BULK_DENSITY_KG_M3.get((material_type or "").strip().lower())
    density_kg = (avg_liters * density / 1000.0) if avg_liters is not None and density else None
    kg_samples = [sample for sample in (vision_kg, density_kg) if sample is not None]
    avg_kg = (sum(kg_samples) / len(kg_samples)) if kg_samples else None

    out: dict = {}
    if avg_liters is not None:
        out["estimated_volume_liters"] = round(avg_liters, 1)
    if avg_kg is not None:
        out["estimated_quantity_kg"] = round(avg_kg, 2)
    if low is not None and high is not None and high >= low:
        out["volume_liters_low"] = round(low, 1)
        out["volume_liters_high"] = round(high, 1)
    if out:
        out["volume_source"] = "vision"
    return out


def attach_volume_estimate(result: dict, payload: dict) -> dict:
    """Copy averaged volume onto a successful classification."""
    if result.get("error") or not result.get("material_type"):
        return result
    volume = average_volume_from_vision(payload, str(result["material_type"]))
    if volume:
        result.update(volume)
    return result


def parse_vision_classification(raw: str) -> Optional[dict]:
    """Parse a vision model JSON payload into a classifier-style result."""
    try:
        payload = json.loads(_strip_json_wrapper(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    label = normalize_vision_label(str(payload.get("label") or payload.get("material") or ""))
    if label not in VISION_LABELS and label not in AMBIGUOUS_CNN_LABELS:
        label = "not_scrap"
    try:
        confidence = float(payload.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    result = classification_from_label(label, confidence, source="vision")
    return attach_volume_estimate(result, payload)


def classification_from_label(label: str, confidence: float, source: str) -> dict:
    if label == "unknown":
        return {"error": "low_confidence", "confidence": confidence, "source": source}
    parent = _SUBTYPE_PARENT.get(label)
    if parent and confidence < 0.45:
        return {
            "error": "ambiguous_material",
            "category": parent,
            "confidence": confidence,
            "source": source,
        }
    if label in NOT_SCRAP_LABELS:
        return {
            "error": "not_scrap",
            "category": label,
            "confidence": confidence,
            "source": source,
        }

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
        reserve_llm("vision")
    except QuotaExceededError:
        logger.warning("Vision skipped: API budget exhausted")
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
                    max_completion_tokens=settings.GROQ_VISION_MAX_TOKENS,
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
        volume = _volume_suffix(result, lang)
        if result.get("error") in {"not_scrap", "unsupported_material", "classification_failed"}:
            return _not_scrap_reply(lang)
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
            return f"यह {name} लगता है।{volume}"
        if lang == "hi-latn":
            return f"Yeh {name} lag raha hai.{volume}"
        if lang == "ur":
            return f"یہ {name} لگ رہا ہے۔{volume}"
        if lang == "ur-latn":
            return f"Yeh {name} lag raha hai.{volume}"
        if lang in {"te", "te-latn"}:
            return f"Idi {name} la undi.{volume}"
        return f"That looks like: {name}.{volume}"


def _fmt_qty(value: float) -> str:
    if value >= 10:
        return f"{value:.0f}"
    text = f"{value:.1f}"
    return text.rstrip("0").rstrip(".")


def _volume_suffix(result: dict, lang: str) -> str:
    kg = result.get("estimated_quantity_kg")
    liters = result.get("estimated_volume_liters")
    if kg is None and liters is None:
        return ""
    kg_txt = _fmt_qty(float(kg)) if kg is not None else None
    liters_txt = _fmt_qty(float(liters)) if liters is not None else None
    if lang == "hi":
        if kg_txt and liters_txt:
            return f" तस्वीर में करीब {kg_txt} किलो (~{liters_txt} लीटर) माल दिख रहा है।"
        if kg_txt:
            return f" तस्वीर में करीब {kg_txt} किलो माल दिख रहा है।"
        return f" तस्वीर में करीब {liters_txt} लीटर माल दिख रहा है।"
    if lang in {"hi-latn", "ur-latn"}:
        if kg_txt and liters_txt:
            return f" Photo mein lagbhag {kg_txt} kg (~{liters_txt} L) maal dikh raha hai."
        if kg_txt:
            return f" Photo mein lagbhag {kg_txt} kg maal dikh raha hai."
        return f" Photo mein lagbhag {liters_txt} L maal dikh raha hai."
    if lang == "ur":
        if kg_txt and liters_txt:
            return f" تصویر میں تقریباً {kg_txt} کلو (~{liters_txt} لیٹر) مال نظر آ رہا ہے۔"
        if kg_txt:
            return f" تصویر میں تقریباً {kg_txt} کلو مال نظر آ رہا ہے۔"
        return f" تصویر میں تقریباً {liters_txt} لیٹر مال نظر آ رہا ہے۔"
    if lang in {"te", "te-latn"}:
        if kg_txt and liters_txt:
            return f" Photo lo sroughaga {kg_txt} kg (~{liters_txt} L) undi."
        if kg_txt:
            return f" Photo lo sroughaga {kg_txt} kg undi."
        return f" Photo lo sroughaga {liters_txt} L undi."
    if kg_txt and liters_txt:
        return f" About {kg_txt} kg visible (~{liters_txt} L)."
    if kg_txt:
        return f" About {kg_txt} kg visible."
    return f" About {liters_txt} L visible."


image_service = ImageService()

# Standalone function exports for backwards compatibility
def classify_image(image_path: str) -> dict:
    return image_service.classify_image(image_path)


def friendly_name(material: str) -> str:
    return image_service.friendly_name(material)


def format_classification_reply(result: dict, language: str = "") -> str:
    return image_service.format_classification_reply(result, language)


def detected_material_tag(classification: dict) -> str:
    """Internal fact tag for the agent. Volume is a photo estimate, not a sale."""
    parts = [
        f"detected_material: {classification.get('material_type')}",
        f"confidence: {float(classification.get('confidence') or 0):.2f}",
    ]
    kg = classification.get("estimated_quantity_kg")
    liters = classification.get("estimated_volume_liters")
    if kg is not None:
        parts.append(f"volume_kg: {float(kg):.2f}")
    if liters is not None:
        parts.append(f"volume_l: {float(liters):.1f}")
    return f"[{', '.join(parts)}]"


def attach_photo_volume(price: Optional[object], classification: dict) -> Optional[object]:
    """Copy vision volume onto a price card without treating it as a sale."""
    if price is None:
        return None
    kg = classification.get("estimated_quantity_kg")
    liters = classification.get("estimated_volume_liters")
    if kg is None and liters is None:
        return price
    updates = {
        "estimated_quantity_kg": kg,
        "estimated_volume_liters": liters,
        "volume_source": classification.get("volume_source") or classification.get("source"),
    }
    if hasattr(price, "model_copy"):
        return price.model_copy(update=updates)
    if isinstance(price, dict):
        merged = dict(price)
        merged.update(updates)
        return merged
    return price
