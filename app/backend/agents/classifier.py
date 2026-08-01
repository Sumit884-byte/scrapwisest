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

import anthropic

from app.backend import ml_classifier_model

logger = logging.getLogger(__name__)

ANTHROPIC_MODEL = "claude-sonnet-4-6"
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
        return cache[abs_path]

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    prompt = (
        "You are helping classify a waste material for a recycling sorting system. "
        f"Known categories are: {', '.join(known_classes)}. "
        "Look at the image and decide the material category. If it clearly doesn't "
        "fit any known category, propose a short new category name instead. "
        "Respond with ONLY a JSON object of the form "
        '{"category": "<name>", "confidence": <float between 0 and 1>} and nothing else.'
    )
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=200,
        messages=[{
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
    except json.JSONDecodeError:
        logger.warning("Vision LLM returned non-JSON output, defaulting to unknown")
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


def classify_image(image_path: str) -> dict:
    """Entry point the orchestrator calls: photo -> material classification."""
    if _bundle is None:
        return {
            "error": (
                "Classifier model not found. Place scrapsense_model.keras and "
                "config.json under models/classifier/."
            )
        }

    label, confidence = ml_classifier_model.predict(_bundle, image_path)

    if label == "unknown":
        llm_result = classify_with_vision_llm(image_path, _bundle.class_names)
        log_unknown_example(image_path, llm_result["category"], llm_result["confidence"])
        return {
            "material_type": llm_result["category"],
            "confidence": llm_result["confidence"],
            "source": "vision_llm",
        }

    return {"material_type": label, "confidence": confidence, "source": "cnn"}