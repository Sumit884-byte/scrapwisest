"""
Classifier agent for ScrapSense (secondary feature -- see project overview).

Identifies material from a photo when a picker is unsure. Wraps the trained
EfficientNetB0 model; falls back to a vision LLM for low-confidence images,
and logs those fallbacks toward active-learning class promotion.
"""

from __future__ import annotations

import base64
import csv
import datetime
import json
import logging
from pathlib import Path


from backend import ml_classifier_model

from pathlib import Path
from dotenv import load_dotenv

_ROOT_DIR = Path(__file__).resolve().parent.parent
_BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(_BACKEND_DIR / ".env")
load_dotenv(_ROOT_DIR / ".env")
load_dotenv()

logger = logging.getLogger(__name__)

from langchain_google_genai import ChatGoogleGenerativeAI

model = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    temperature=1.0,  # Gemini 3.0+ defaults to 1.0
    max_tokens=None,
    timeout=None,
    max_retries=2,
    # other params...
)


LLM_CACHE_PATH = Path("data/vision_llm_cache.json")
ACTIVE_LEARNING_LOG_PATH = Path("data/active_learning_log.csv")

_bundle = ml_classifier_model.load()


def _load_cache() -> dict:
    if LLM_CACHE_PATH.exists():
        return json.loads(LLM_CACHE_PATH.read_text())
    return {}


def _save_cache(cache: dict) -> None:
    LLM_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LLM_CACHE_PATH.write_text(json.dumps(cache, indent=2))


def _image_to_base64(image_path: str) -> str:
    return base64.standard_b64encode(Path(image_path).read_bytes()).decode("utf-8")


def _media_type_for(image_path: str) -> str:
    ext = Path(image_path).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


def classify_with_vision_llm(image_path: str, known_classes: list) -> dict:
    """Vision-LLM fallback for low-confidence CNN predictions, cached to disk."""
    abs_path = str(Path(image_path).resolve())
    cache = _load_cache()
    if abs_path in cache:
        logger.info("Vision LLM cache hit for image: %s -> %s", abs_path, cache[abs_path])
        return cache[abs_path]

    logger.info("Invoking Vision LLM fallback for low-confidence image: %s", abs_path)
    prompt = (
        "You are helping classify a waste material for a recycling sorting system. "
        f"Known categories are: {', '.join(known_classes)}. "
        "Look at the image and decide the material category. If it clearly doesn't "
        "fit any known category, propose a short new category name instead. "
        "Respond with ONLY a JSON object of the form "
        '{"category": "<name>", "confidence": <float between 0 and 1>} and nothing else.'
    )
    response = model.invoke([
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": _media_type_for(abs_path),
                        "data": _image_to_base64(abs_path),
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    try:
        result = json.loads(text)
        logger.info("Vision LLM returned classification: %s", result)
    except json.JSONDecodeError:
        logger.warning("Vision LLM returned non-JSON output ('%s'), defaulting to unknown", text)
        result = {"category": "unknown", "confidence": 0.0}

    cache[abs_path] = result
    _save_cache(cache)
    return result


def log_unknown_example(image_path: str, llm_label: str, llm_confidence: float) -> None:
    ACTIVE_LEARNING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not ACTIVE_LEARNING_LOG_PATH.exists()
    with open(ACTIVE_LEARNING_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["image_path", "llm_label", "llm_confidence", "timestamp"])
        writer.writerow([
            image_path, llm_label, llm_confidence,
            datetime.datetime.now().isoformat(timespec="seconds"),
        ])
    logger.info(
        "Logged active-learning sample to %s: label='%s', confidence=%.2f",
        ACTIVE_LEARNING_LOG_PATH,
        llm_label,
        llm_confidence,
    )


DEFAULT_CLASSES = [
    "plastic_pet", "plastic_hdpe", "glass", "metal_aluminum",
    "metal_steel", "cardboard", "mixed_paper", "other"
]

def classify_image(image_path: str) -> dict:
    """Entry point the orchestrator calls: photo -> material classification."""
    global _bundle
    logger.info("Starting image classification pipeline for: %s", image_path)
    if _bundle is None:
        _bundle = ml_classifier_model.load()

    if _bundle is None:
        logger.warning("Classifier model bundle is None. Falling back directly to Vision LLM...")
        llm_result = classify_with_vision_llm(image_path, DEFAULT_CLASSES)
        log_unknown_example(image_path, llm_result.get("category", "unknown"), llm_result.get("confidence", 0.0))
        return {
            "material_type": llm_result.get("category", "other"),
            "confidence": llm_result.get("confidence", 0.7),
            "source": "vision_llm",
        }

    label, confidence = ml_classifier_model.predict(_bundle, image_path)

    if label == "unknown":
        logger.info("CNN outcome was unknown/low confidence. Triggering Vision LLM fallback...")
        llm_result = classify_with_vision_llm(image_path, _bundle.class_names)
        log_unknown_example(image_path, llm_result["category"], llm_result["confidence"])
        res = {
            "material_type": llm_result["category"],
            "confidence": llm_result["confidence"],
            "source": "vision_llm",
        }
        logger.info("Classification completed via Vision LLM fallback: %s", res)
        return res

    res = {"material_type": label, "confidence": confidence, "source": "cnn"}
    logger.info("Classification completed via CNN model: %s", res)
    return res
