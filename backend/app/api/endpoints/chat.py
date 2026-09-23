"""
Chat endpoint: accepts text message and optional photo upload.
Processes photo classification ahead of the agent reasoning loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from langchain_core.messages import AIMessage

from app.agent.main_agent import AgentContext, get_agent
from app.agent.tool_outputs import begin, end
from app.agent.nemotron import normalize_region, region_info
from app.core.config import settings
from app.repositories.report_repository import report_repo
from app.schemas.chat import ChatResponse, ReportReviewData
from app.schemas.price import PriceEstimate
from app.schemas.report import MaterialType, PriceReport
from app.services.price_estimator import price_estimator_service
from app.services.image_service import image_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_TIER_PAREN = re.compile(
    r"\s*\((?:city[- ]level|local|seed|neighborhood|medium|high|low)[^)]*\)",
    re.IGNORECASE,
)
_MATERIAL_ONLY = {
    "pet": MaterialType.PLASTIC_PET,
    "hdpe": MaterialType.PLASTIC_HDPE,
    "aluminum": MaterialType.METAL_ALUMINUM,
    "aluminium": MaterialType.METAL_ALUMINUM,
    "steel": MaterialType.METAL_STEEL,
    "glass": MaterialType.GLASS,
    "cardboard": MaterialType.CARDBOARD,
}
_MATERIAL_LABEL = {
    MaterialType.PLASTIC_PET: "PET",
    MaterialType.PLASTIC_HDPE: "HDPE",
    MaterialType.METAL_ALUMINUM: "aluminum",
    MaterialType.METAL_STEEL: "steel",
    MaterialType.GLASS: "glass",
    MaterialType.CARDBOARD: "cardboard",
    MaterialType.MIXED_PAPER: "paper",
}
_HI_WORDS = {
    "pet": "पीईटी",
    "hdpe": "एचडीपीई",
    "aluminum": "एल्युमिनियम",
    "aluminium": "एल्युमिनियम",
    "steel": "स्टील",
    "glass": "कांच",
    "cardboard": "गत्ता",
    "paper": "कागज",
    "plastic": "प्लास्टिक",
    "metal": "धातु",
    "india": "भारत",
    "pakistan": "पाकिस्तान",
    "bangladesh": "बांग्लादेश",
    "nepal": "नेपाल",
    "kolkata": "कोलकाता",
    "calcutta": "कोलकाता",
    "mumbai": "मुंबई",
    "delhi": "दिल्ली",
    "karachi": "कराची",
    "lahore": "लाहौर",
    "multan": "मुल्तान",
    "dhaka": "ढाका",
    "hyderabad": "हैदराबाद",
    "unknown": "",
}


def clean_reply(text: str) -> str:
    """Drop leaked tiers and repeated sentences from model output."""
    cleaned = _TIER_PAREN.sub("", text or "").strip()
    chunks = [part.strip() for part in re.split(r"\n+", cleaned) if part.strip()]
    unique: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        key = re.sub(r"\s+", " ", chunk).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return "\n".join(unique)


def parse_material_reply(text: str) -> Optional[MaterialType]:
    """Treat a short one-word answer (PET, HDPE, …) as the material they just confirmed."""
    tokens = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).split()
    if not tokens or len(tokens) > 3:
        return None
    joined = " ".join(tokens)
    if joined in _MATERIAL_ONLY:
        return _MATERIAL_ONLY[joined]
    if len(tokens) == 1:
        return _MATERIAL_ONLY.get(tokens[0])
    if tokens[-1] in _MATERIAL_ONLY and tokens[0] in {"its", "it", "is", "the"}:
        return _MATERIAL_ONLY[tokens[-1]]
    return None


def _format_rate(amount: float) -> str:
    return f"{amount:.0f}" if float(amount).is_integer() else f"{amount:.1f}"


def join_place(city: str = "", country: str = "") -> str:
    return ", ".join(part.strip() for part in (city, country) if part and part.strip())


_REPLY_LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi (Devanagari script, not Hinglish)",
    "hi-latn": "Hinglish (Roman letters)",
    "ur": "Urdu (Arabic script)",
    "ur-latn": "Roman Urdu",
    "te": "Telugu (Telugu script)",
    "te-latn": "Roman Telugu",
}


def picker_context_tags(
    language: str = "",
    city: str = "",
    country: str = "",
    currency: str = "",
    neighborhood: str = "",
) -> str:
    bits: list[str] = []
    place = join_place(city, country)
    if place:
        bits.append(f"[picker_place: {place}]")
    if neighborhood and neighborhood.strip():
        bits.append(f"[picker_neighborhood: {neighborhood.strip()}]")
    if currency and currency.strip():
        bits.append(f"[picker_currency: {currency.strip().upper()}]")
    lang = language.strip().lower()
    if lang and lang != "auto":
        label = _REPLY_LANGUAGE_NAMES.get(lang, language.strip())
        bits.append(f"[reply_language: {label}]")
    return "\n".join(bits)


def with_picker_context(
    text: str,
    language: str = "",
    city: str = "",
    country: str = "",
    currency: str = "",
    neighborhood: str = "",
) -> str:
    tags = picker_context_tags(language, city, country, currency, neighborhood)
    if not tags:
        return text
    if text.strip():
        return f"{text.strip()}\n\n{tags}"
    return tags


def hindi_words(text: str) -> str:
    """Swap known English material/place tokens for Hindi so a Hindi reply stays Hindi."""
    if not text:
        return ""
    parts = re.split(r"([,\s]+)", text)
    out: list[str] = []
    for part in parts:
        key = part.strip().casefold()
        if key in _HI_WORDS:
            out.append(_HI_WORDS[key])
        else:
            out.append(part)
    return re.sub(r"\s+,", ",", "".join(out)).strip(" ,")


def _material_rate_reply(label: str, price: str, place: str, language: str) -> str:
    lang = (language or "").strip().lower()
    if lang in {"hi"}:
        hi_label = hindi_words(label) or label
        hi_place = hindi_words(place)
        return (
            f"{hi_label} की कीमत {hi_place} में लगभग {price} रुपए किलो है।"
            if hi_place
            else f"{hi_label} की कीमत लगभग {price} रुपए किलो है।"
        )
    if lang in {"hi-latn"}:
        return (
            f"{label} ka rate {place} mein lagbhag {price} rupay kilo hai."
            if place
            else f"{label} ka rate lagbhag {price} rupay kilo hai."
        )
    if lang in {"ur"}:
        return (
            f"{label} کا ریٹ {place} میں تقریباً {price} روپے کلو ہے۔"
            if place
            else f"{label} کا ریٹ تقریباً {price} روپے کلو ہے۔"
        )
    if lang in {"ur-latn"}:
        return (
            f"{label} ka rate {place} mein taqreeban {price} rupay kilo hai."
            if place
            else f"{label} ka rate taqreeban {price} rupay kilo hai."
        )
    if lang in {"te", "te-latn"}:
        return (
            f"{place} lo {label} rate sumaru {price} rupayalu kilo."
            if place
            else f"{label} rate sumaru {price} rupayalu kilo."
        )
    return f"{label} is {price} rupees per kg in {place}." if place else f"{label} is about {price} rupees per kg."


def _material_rate_response(
    material: MaterialType,
    location: str = "unknown",
    language: str = "",
    currency: str = "",
    country: str = "",
    city: str = "",
    neighborhood: str = "",
) -> ChatResponse:
    estimate = price_estimator_service.estimate(
        material,
        location,
        currency=(currency.strip() or "unknown"),
        country=country.strip() or None,
        city=city.strip() or None,
        neighborhood=neighborhood.strip() or None,
    )
    label = _MATERIAL_LABEL.get(material, material.value.replace("_", " "))
    price = _format_rate(estimate.estimated_price_per_kg)
    place = (estimate.location or "").strip()
    if place.lower() == "unknown":
        place = ""
    return ChatResponse(
        reply=_material_rate_reply(label, price, place, language),
        price_data=estimate,
    )


def _extract_reply(agent_result: dict) -> str:
    """Extract the last AI response text from the agent's message list."""
    for msg in reversed(agent_result.get("messages", [])):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, str) and content.strip():
            return clean_reply(content)
        if isinstance(content, list):
            texts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            joined = "\n".join(t for t in texts if t).strip()
            if joined:
                return clean_reply(joined)
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


def _report_price_value(raw: dict, *names: str, default=0):
    """Read a money field under its new or legacy key."""
    for name in names:
        if raw.get(name) is not None:
            return raw[name]
    return default


def _extract_report_data(agent_result: dict) -> Optional[ReportReviewData]:
    """Recover a sale report and anomaly status from the pipeline output."""
    for item in _walk_values(agent_result):
        raw = item.get("price_report") if isinstance(item, dict) else None
        if raw is None and (
            {"material_type", "quantity_kg", "price_per_kg"}.issubset(item)
            or {"material_type", "quantity_kg", "price_paid_pkr_per_kg"}.issubset(item)
        ):
            raw = item
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump()
        if not isinstance(raw, dict):
            continue
        if not (
            {"material_type", "quantity_kg", "price_per_kg"}.issubset(raw)
            or {"material_type", "quantity_kg", "price_paid_pkr_per_kg"}.issubset(raw)
        ):
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
                total_price=_report_price_value(raw, "total_price", "price_paid_pkr"),
                price_per_kg=_report_price_value(
                    raw, "price_per_kg", "price_paid_pkr_per_kg"
                ),
                currency=raw.get("currency", "unknown"),
                country=raw.get("country"),
                city=raw.get("city"),
                neighborhood=raw.get("neighborhood"),
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


def _remember_thread(tf_region: str | None, picker_id: str, user_text: str, assistant_text: str) -> None:
    """Keep photo / short-answer turns in the agent thread for the next message."""
    try:
        get_agent(tf_region).update_state(
            {"configurable": {"thread_id": picker_id}},
            {
                "messages": [
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": assistant_text},
                ]
            },
        )
    except Exception:
        logger.warning("Could not persist turn to agent thread", exc_info=True)


def _invoke_agent(tf_region: str | None, text: str, agent_config: dict, agent_context: AgentContext):
    begin(agent_context.picker_id)
    try:
        result = get_agent(tf_region).invoke(
            {"messages": [{"role": "user", "content": text}]},
            config=agent_config,
            context=agent_context,
        )
        return result, *end(agent_context.picker_id)
    except Exception:
        end(agent_context.picker_id)
        raise


def _as_price_data(value) -> Optional[PriceEstimate]:
    if isinstance(value, PriceEstimate):
        return value
    if isinstance(value, dict):
        try:
            return PriceEstimate.model_validate(value)
        except Exception:
            return None
    return None


def _as_report_data(value) -> Optional[ReportReviewData]:
    if isinstance(value, ReportReviewData):
        return value
    if isinstance(value, dict):
        try:
            return ReportReviewData.model_validate(value)
        except Exception:
            return None
    return None


def _chat_response(
    agent_result: dict,
    region_id: str | None = None,
    price_data: Optional[PriceEstimate] = None,
    report_data: Optional[ReportReviewData] = None,
) -> ChatResponse:
    return ChatResponse(
        reply=_extract_reply(agent_result),
        price_data=_as_price_data(price_data),
        report_data=_as_report_data(report_data) or _extract_report_data(agent_result),
        region=region_info(region_id)["id"],
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
        total_price=pending.total_price,
        price_per_kg=pending.price_per_kg,
        currency=pending.currency,
        country=pending.country,
        city=pending.city,
        neighborhood=pending.neighborhood,
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
                total_price=data.total_price,
                price_per_kg=data.price_per_kg,
                currency=data.currency,
                country=data.country,
                city=data.city,
                neighborhood=data.neighborhood,
                location=data.location,
                timestamp=datetime.now(timezone.utc),
                needs_confirmation=True,
                confirmation_reason=data.confirmation_reason or data.anomaly_reason,
                picker_id=picker_id,
            )
        )
    return response


def _demo_price_response(text: str, currency: str = "", country: str = "", city: str = "", neighborhood: str = "") -> ChatResponse:
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
    estimate = price_estimator_service.estimate(
        material,
        neighborhood.strip() or location,
        currency=(currency.strip() or "unknown"),
        country=country.strip() or None,
        city=city.strip() or None,
        neighborhood=neighborhood.strip() or None,
    )
    unit = estimate.currency if estimate.currency.lower() != "unknown" else "PKR"
    reply = (
        f"Demo estimate: {estimate.estimated_price_per_kg:.0f} {unit} per kg for "
        f"{material.value.replace('_', ' ')} in {location}."
    )
    return ChatResponse(reply=reply, price_data=estimate)


def _deterministic_price_fallback(text: str, currency: str = "", country: str = "", city: str = "", neighborhood: str = "") -> Optional[ChatResponse]:
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
    estimate = price_estimator_service.estimate(
        material,
        neighborhood.strip() or location,
        currency=(currency.strip() or "unknown"),
        country=country.strip() or None,
        city=city.strip() or None,
        neighborhood=neighborhood.strip() or None,
    )
    unit = estimate.currency if estimate.currency.lower() != "unknown" else "PKR"
    return ChatResponse(
        reply=(
            f"The current fallback estimate is about "
            f"{estimate.estimated_price_per_kg:.0f} {unit} per kg for {material.value.replace('_', ' ')}."
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
    region: str = Form(
        "",
        description="Optional Token Factory region (eu-north1 or us-central1).",
    ),
    language: str = Form(""),
    city: str = Form(""),
    country: str = Form(""),
    currency: str = Form(
        "",
        description="Optional ISO 4217 currency code for this picker's market (e.g. PKR, INR, USD).",
    ),
    neighborhood: str = Form(
        "",
        description="Optional neighborhood/area within the city.",
    ),
):
    text = message.strip()
    tf_region = normalize_region(region)
    place = join_place(city, country) or "unknown"
    logger.info(
        "=== POST /chat received: picker_id='%s' text='%s' image=%s region=%s place='%s' lang='%s'",
        picker_id, text, image.filename if image else None, tf_region, place, language,
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
        return _demo_price_response(text, currency, country, city, neighborhood)

    agent_config = {"configurable": {"thread_id": picker_id}}
    agent_context = AgentContext(picker_id=picker_id)

    confirmed = parse_material_reply(text) if text and image is None else None
    if confirmed is not None:
        logger.info("Path A: short material answer '%s' → %s", text, confirmed.value)
        response = _material_rate_response(
            confirmed,
            neighborhood.strip() or place,
            language,
            currency,
            country,
            city,
            neighborhood,
        )
        await asyncio.to_thread(
            _remember_thread,
            tf_region,
            picker_id,
            with_picker_context(text, language, city, country, currency, neighborhood),
            response.reply,
        )
        return response

    # Path A: Text-only request
    if image is None:
        logger.info("Path A: Text-only request. Invoking deep agent...")
        try:
            agent_result, captured_price, captured_report = await asyncio.to_thread(
                _invoke_agent,
                tf_region,
                with_picker_context(text, language, city, country, currency, neighborhood),
                agent_config,
                agent_context,
            )
        except Exception as exc:
            logger.exception("Agent invocation failed for text-only path")
            if settings.ENABLE_LLM_FALLBACKS:
                fallback = _deterministic_price_fallback(text, currency, country, city, neighborhood)
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
        return _persist_pending_review(
            _chat_response(agent_result, tf_region, captured_price, captured_report),
            picker_id,
        )

    # Path B & C: Photo attached
    logger.info("Processing attached image first...")
    image_path = await image_service.save_image(image)
    try:
        classification = await asyncio.to_thread(image_service.classify_image, image_path)
        logger.info("Image classification outcome: %s", classification)
    except Exception:
        logger.exception("Classification failed unexpectedly")
        classification = {"error": "classification_failed"}
    finally:
        await asyncio.to_thread(image_service.cleanup_image, image_path)

    # Photo only, no text -> classification IS the answer. Agent never runs.
    if not text:
        logger.info("Path B: Photo only (no text). Generating direct static reply...")
        reply = image_service.format_classification_reply(classification, language)
        logger.info("Classification reply: '%s'", reply)
        if classification.get("error") == "ambiguous_material":
            photo_tag = f"[image_material_ambiguous: {classification.get('category', 'unknown')}]"
        elif "error" in classification:
            photo_tag = "[image_analysis_failed]"
        else:
            photo_tag = (
                f"[detected_material: {classification.get('material_type')}, "
                f"confidence: {classification.get('confidence', 0):.2f}]"
            )
        await asyncio.to_thread(
            _remember_thread,
            tf_region,
            picker_id,
            with_picker_context(photo_tag, language, city, country, currency, neighborhood),
            reply,
        )
        return ChatResponse(reply=reply, region=region_info(tf_region)["id"])

    # Photo + text -> fold classification into message as fact
    logger.info("Path C: Photo + Text. Ingesting classification tag into message...")
    if classification.get("error") == "ambiguous_material":
        tag = f"[image_material_ambiguous: {classification.get('category', 'unknown')}]"
    elif "error" in classification:
        tag = "[image_analysis_failed]"
    else:
        tag = f"[detected_material: {classification['material_type']}, confidence: {classification['confidence']:.2f}]"

    augmented_content = with_picker_context(
        f"{text}\n\n{tag}", language, city, country, currency, neighborhood
    )
    logger.info("Invoking deep agent with augmented content: '%s'", augmented_content)

    try:
        agent_result, captured_price, captured_report = await asyncio.to_thread(
            _invoke_agent,
            tf_region,
            augmented_content,
            agent_config,
            agent_context,
        )
    except Exception:
        logger.exception("Agent invocation failed for photo+text path")
        raise HTTPException(
            status_code=500, detail="Something went wrong processing your message."
        )

    reply = _extract_reply(agent_result)
    logger.info("Deep agent reply extracted: '%s'", reply)
    return _persist_pending_review(
        _chat_response(agent_result, tf_region, captured_price, captured_report),
        picker_id,
    )
