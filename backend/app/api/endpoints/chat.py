"""
Chat endpoint: accepts text message and optional photo upload.
Processes photo classification ahead of the agent reasoning loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from langchain_core.messages import AIMessage

from app.agent.main_agent import AgentContext, get_agent
from app.core.config import settings
from app.schemas.chat import ChatResponse, ReportReviewData
from app.schemas.price import PriceEstimate
from app.schemas.report import MaterialType
from app.services.price_estimator import price_estimator_service
from app.services.image_service import image_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _extract_reply(agent_result: dict) -> str:
    """Extract the last AI response text from the agent's message list."""
    for msg in reversed(agent_result.get("messages", [])):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            texts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            joined = "\n".join(t for t in texts if t).strip()
            if joined:
                return joined
    return "Sorry, I couldn't come up with a response."


def _extract_price_data(agent_result: dict) -> Optional[PriceEstimate]:
    """Recover structured output from the estimate_price tool, when present."""
    for msg in reversed(agent_result.get("messages", [])):
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content")

        candidates = content if isinstance(content, list) else [content]
        for candidate in candidates:
            value = candidate.get("text") if isinstance(candidate, dict) and "text" in candidate else candidate
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (TypeError, ValueError):
                    continue
            if not isinstance(value, dict):
                continue
            if not {"estimated_price_per_kg", "material_type", "tier_used"}.issubset(value):
                continue
            try:
                return PriceEstimate.model_validate(value)
            except Exception:
                logger.debug("Ignoring malformed price tool output", exc_info=True)
    return None


def _walk_values(value):
    """Yield nested dictionaries from model, tool, and message outputs."""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def _extract_report_data(agent_result: dict) -> Optional[ReportReviewData]:
    """Recover a sale report and anomaly status from the pipeline output."""
    for item in _walk_values(agent_result):
        raw = item.get("price_report") if isinstance(item, dict) else None
        if raw is None and {"material_type", "quantity_kg", "price_paid_pkr_per_kg"}.issubset(item):
            raw = item
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump()
        if not isinstance(raw, dict):
            continue
        if not {"material_type", "quantity_kg", "price_paid_pkr_per_kg"}.issubset(raw):
            continue

        verdict = item.get("verdict")
        if hasattr(verdict, "model_dump"):
            verdict = verdict.model_dump()
        if not isinstance(verdict, dict):
            verdict = {}
        try:
            return ReportReviewData(
                material_type=raw["material_type"],
                quantity_kg=raw.get("quantity_kg", 0),
                price_paid_pkr=raw.get("price_paid_pkr", 0),
                price_paid_pkr_per_kg=raw["price_paid_pkr_per_kg"],
                location=raw.get("location", "unknown"),
                needs_confirmation=raw.get("needs_confirmation", False),
                confirmation_reason=raw.get("confirmation_reason"),
                is_anomalous=verdict.get("is_anomalous", False),
                anomaly_reason=verdict.get("reason"),
                anomaly_method=verdict.get("method"),
            )
        except Exception:
            logger.debug("Ignoring malformed report pipeline output", exc_info=True)
    return None


def _chat_response(agent_result: dict) -> ChatResponse:
    return ChatResponse(
        reply=_extract_reply(agent_result),
        price_data=_extract_price_data(agent_result),
        report_data=_extract_report_data(agent_result),
    )


def _demo_price_response(text: str) -> ChatResponse:
    """Provide a no-API-key response for local UI testing only."""
    lowered = text.lower()
    material_aliases = (
        (MaterialType.PLASTIC_PET, ("pet", "plastic")),
        (MaterialType.PLASTIC_HDPE, ("hdpe",)),
        (MaterialType.METAL_ALUMINUM, ("aluminum", "aluminium")),
        (MaterialType.METAL_STEEL, ("steel",)),
        (MaterialType.CARDBOARD, ("cardboard",)),
        (MaterialType.MIXED_PAPER, ("paper",)),
        (MaterialType.GLASS, ("glass",)),
    )
    material = next(
        (candidate for candidate, aliases in material_aliases if any(alias in lowered for alias in aliases)),
        MaterialType.PLASTIC_PET,
    )
    location = "Income Colony" if "income colony" in lowered else "Samejabad"
    estimate = price_estimator_service.estimate(material, location)
    reply = (
        f"Demo estimate: {estimate.estimated_price_per_kg:.0f} PKR per kg for "
        f"{material.value.replace('_', ' ')} in {location}."
    )
    return ChatResponse(reply=reply, price_data=estimate)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    message: str = Form(""),
    picker_id: str = Form(
        ...,
        description="Stable per-picker id from client device for continuity and memory.",
    ),
    image: Optional[UploadFile] = File(None),
):
    text = message.strip()
    logger.info(
        "=== POST /chat received: picker_id='%s' text='%s' image=%s",
        picker_id, text, image.filename if image else None,
    )

    if not text and image is None:
        logger.warning("Rejected /chat request: neither text nor image was provided.")
        raise HTTPException(status_code=400, detail="Provide a message, an image, or both.")

    if settings.DEMO_MODE and image is None:
        logger.info("DEMO_MODE enabled: returning deterministic local estimate")
        return _demo_price_response(text)

    agent_config = {"configurable": {"thread_id": picker_id}}
    agent_context = AgentContext(picker_id=picker_id)

    # Path A: Text-only request
    if image is None:
        logger.info("Path A: Text-only request. Invoking deep agent...")
        try:
            agent_result = await asyncio.to_thread(
                get_agent().invoke,
                {"messages": [{"role": "user", "content": text}]},
                config=agent_config,
                context=agent_context,
            )
        except Exception as exc:
            logger.exception("Agent invocation failed for text-only path")
            detail = (
                str(exc)
                if "NEBIUS_API_KEY" in str(exc)
                else "Something went wrong processing your message."
            )
            raise HTTPException(status_code=500, detail=detail) from exc

        reply = _extract_reply(agent_result)
        logger.info("Deep agent reply extracted: '%s'", reply)
        return _chat_response(agent_result)

    # Path B & C: Photo attached
    logger.info("Processing attached image first...")
    image_path = await image_service.save_image(image)
    try:
        classification = await asyncio.to_thread(image_service.classify_image, image_path)
        logger.info("Image classification outcome: %s", classification)
    except Exception:
        logger.exception("Classification failed unexpectedly")
        classification = {"error": "classification_failed"}

    # Photo only, no text -> classification IS the answer. Agent never runs.
    if not text:
        logger.info("Path B: Photo only (no text). Generating direct static reply...")
        reply = image_service.format_classification_reply(classification)
        logger.info("Classification reply: '%s'", reply)
        return ChatResponse(reply=reply)

    # Photo + text -> fold classification into message as fact
    logger.info("Path C: Photo + Text. Ingesting classification tag into message...")
    if "error" in classification:
        tag = "[image_analysis_failed]"
    else:
        tag = f"[detected_material: {classification['material_type']}, confidence: {classification['confidence']:.2f}]"

    augmented_content = f"{text}\n\n{tag}"
    logger.info("Invoking deep agent with augmented content: '%s'", augmented_content)

    try:
        agent_result = await asyncio.to_thread(
            get_agent().invoke,
            {"messages": [{"role": "user", "content": augmented_content}]},
            config=agent_config,
            context=agent_context,
        )
    except Exception:
        logger.exception("Agent invocation failed for photo+text path")
        raise HTTPException(
            status_code=500, detail="Something went wrong processing your message."
        )

    reply = _extract_reply(agent_result)
    logger.info("Deep agent reply extracted: '%s'", reply)
    return _chat_response(agent_result)
