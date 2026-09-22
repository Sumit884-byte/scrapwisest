"""
Chat endpoint: accepts text message and optional photo upload.
Processes photo classification ahead of the agent reasoning loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from langchain_core.messages import AIMessage

from app.agent.main_agent import AgentContext, get_agent
from app.core.config import settings
from app.repositories.report_repository import report_repo
from app.schemas.chat import ChatResponse, ReportReviewData
from app.schemas.price import PriceEstimate
from app.schemas.report import MaterialType, PriceReport
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


def _pending_review_response(text: str, picker_id: str) -> Optional[ChatResponse]:
    """Handle review-card actions without spending another model call."""
    pending = report_repo.get_pending(picker_id)
    if pending is None:
        return None

    lowered = text.lower()
    confirmation = any(
        phrase in lowered
        for phrase in ("details are correct", "accept this report", "accept the sale", "yes, accept")
    )
    correction = any(
        phrase in lowered
        for phrase in ("correct the weight", "correct details", "wrong weight", "wrong price")
    )

    review_data = ReportReviewData(
        material_type=pending.material_type,
        quantity_kg=pending.quantity_kg,
        price_paid_pkr=pending.price_paid_pkr,
        price_paid_pkr_per_kg=pending.price_paid_pkr_per_kg,
        location=pending.location,
    )

    if confirmation:
        pending.needs_confirmation = False
        pending.confirmation_reason = None
        report_repo.add(pending)
        report_repo.clear_pending(picker_id)
        return ChatResponse(
            reply="Your sale details were confirmed and added to the trusted local price data.",
            report_data=review_data,
        )

    if correction:
        review_data.needs_confirmation = True
        review_data.confirmation_reason = "Waiting for corrected weight or total price."
        return ChatResponse(
            reply="Please send the corrected total weight in kilograms and the total rupees you received.",
            report_data=review_data,
        )

    return None


def _persist_pending_review(response: ChatResponse, picker_id: str) -> ChatResponse:
    """Keep reports needing review out of the trusted price pool."""
    if response.report_data and (
        response.report_data.needs_confirmation or response.report_data.is_anomalous
    ):
        data = response.report_data
        report_repo.save_pending(
            PriceReport(
                material_type=data.material_type,
                quantity_kg=data.quantity_kg,
                price_paid_pkr=data.price_paid_pkr,
                price_paid_pkr_per_kg=data.price_paid_pkr_per_kg,
                location=data.location,
                timestamp=datetime.now(timezone.utc),
                needs_confirmation=True,
                confirmation_reason=data.confirmation_reason or data.anomaly_reason,
                picker_id=picker_id,
            )
        )
    return response


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


def _deterministic_price_fallback(text: str) -> Optional[ChatResponse]:
    """Answer simple price questions when the LLM service is unavailable."""
    lowered = text.lower()
    price_words = ("rate", "price", "worth", "qeemat", "dhar", "kitna", "kya hai")
    if not any(word in lowered for word in price_words):
        return None

    aliases = (
        (MaterialType.PLASTIC_HDPE, ("hdpe",)),
        (MaterialType.PLASTIC_PET, ("pet", "plastic")),
        (MaterialType.METAL_ALUMINUM, ("aluminum", "aluminium")),
        (MaterialType.METAL_STEEL, ("steel", "iron", "loha")),
        (MaterialType.CARDBOARD, ("cardboard",)),
        (MaterialType.MIXED_PAPER, ("paper", "kaghaz")),
        (MaterialType.GLASS, ("glass", "sheesha")),
    )
    material = next(
        (candidate for candidate, names in aliases if any(name in lowered for name in names)),
        None,
    )
    if material is None:
        return None

    location = "Income Colony" if "income colony" in lowered else "Samejabad"
    estimate = price_estimator_service.estimate(material, location)
    return ChatResponse(
        reply=(
            f"The current fallback estimate is about "
            f"{estimate.estimated_price_per_kg:.0f} PKR per kg for {material.value.replace('_', ' ')}."
        ),
        price_data=estimate,
    )


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

    if text:
        pending_response = _pending_review_response(text, picker_id)
        if pending_response is not None:
            return pending_response

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
            if settings.ENABLE_LLM_FALLBACKS:
                fallback = _deterministic_price_fallback(text)
                if fallback is not None:
                    return fallback
            detail = (
                str(exc)
                if "NEBIUS_API_KEY" in str(exc) or "XKIRO_API_KEY" in str(exc)
                else "Something went wrong processing your message."
            )
            raise HTTPException(status_code=500, detail=detail) from exc

        reply = _extract_reply(agent_result)
        logger.info("Deep agent reply extracted: '%s'", reply)
        return _persist_pending_review(_chat_response(agent_result), picker_id)

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
    return _persist_pending_review(_chat_response(agent_result), picker_id)
