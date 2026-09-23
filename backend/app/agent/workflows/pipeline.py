"""
Report-to-verdict pipeline workflow for Scrapwisest.
Graph structure:
    START -> extract_report -> validate_and_build --+--> deterministic_check --+--> ml_check --+--> llm_check --> END
                                                      |                        |                |
                                                      | (needs_confirmation)   |                +----------------+--> accept --> END
                                                      v                        |
                                                     END                       +---------------------------------> accept --> END
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timezone
from typing import List, Optional

from langgraph.graph import END, START, StateGraph

from app.agent.models import nano_model, ultra_model
from app.agent.tool_outputs import record_report
from app.agent.workflows.state import PipelineState
from app.core.config import settings
from app.schemas.chat import ReportReviewData
from app.repositories.report_repository import report_repo
from app.schemas.report import (
    AnomalyVerdict,
    LLMJudgment,
    MaterialType,
    PriceReport,
    RawExtraction,
)
from app.services.anomaly_detector import anomaly_detector_service
from app.services.location_resolver import (
    UNKNOWN_CURRENCY,
    is_plausible_currency,
    normalize_currency,
    normalize_location,
    normalize_place_part,
    picker_currency_from_tags,
    picker_neighborhood_from_tags,
    picker_place_from_tags,
    validate_market_fields,
)

logger = logging.getLogger(__name__)

KNOWN_MATERIALS = [m.value for m in MaterialType]

PRICE_PER_KG_BANDS = {
    MaterialType(k): v for k, v in settings.PRICE_PER_KG_BANDS.items()
}


def _material_label(material) -> str:
    return material.value if hasattr(material, "value") else str(material)


def _capture_report(price_report: PriceReport, verdict: Optional[AnomalyVerdict] = None) -> None:
    verdict_data = verdict.model_dump() if verdict is not None else {}
    record_report(
        ReportReviewData(
            material_type=price_report.material_type,
            quantity_kg=price_report.quantity_kg,
            total_price=price_report.total_price,
            price_per_kg=price_report.price_per_kg,
            currency=price_report.currency,
            country=price_report.country,
            city=price_report.city,
            neighborhood=price_report.neighborhood,
            location=price_report.location,
            needs_confirmation=price_report.needs_confirmation,
            confirmation_reason=price_report.confirmation_reason,
            is_anomalous=bool(verdict_data.get("is_anomalous", False)),
            anomaly_reason=verdict_data.get("reason"),
            anomaly_method=verdict_data.get("method"),
        )
    )

_structured_extraction_model = None
_structured_llm_judge = None


def _extraction_model():
    global _structured_extraction_model
    if _structured_extraction_model is None:
        _structured_extraction_model = nano_model().with_structured_output(RawExtraction)
    return _structured_extraction_model


def _judge_model():
    global _structured_llm_judge
    if _structured_llm_judge is None:
        _structured_llm_judge = ultra_model().with_structured_output(LLMJudgment)
    return _structured_llm_judge


EXTRACTION_PROMPT = """You are extracting a scrap sale report from a waste \
picker's message. The message may be in any language or informal phrasing, \
and may contain speech-to-text errors. Pickers sell in many countries and \
currencies -- never assume one.

Extract these fields:
- material_type: must be exactly one of {material_list}. If genuinely \
unclear, use "other".
- quantity_kg: weight sold, in kilograms. Convert if given in another unit.
- total_price: TOTAL amount paid (number only, not per-kg, unless \
that's explicitly how it was stated -- then multiply it out).
- currency: 3-letter currency code ONLY if explicitly stated in the \
message (e.g. "500 PKR", "INR 700", "20 dollars" implies USD). A bare \
"Rs"/"rupay" alone is ambiguous across countries -- leave it empty. \
Never guess.
- country / city / neighborhood: place parts if the message names them \
(e.g. "Karol Bagh" is a neighborhood, "Delhi" a city). Leave any missing \
part empty -- do not guess. Context tags like [picker_place: ...] or \
[picker_currency: ...] carry the picker's saved settings and may be used \
for place/currency when the sale itself states nothing different.
- location_text: raw area phrase as written, if any.

For each field, give a confidence score from 0 to 1. If you are genuinely \
guessing (an ambiguous number, an unclear material), add that field's name \
to unclear_fields and lower its confidence. Do not silently pick the most \
likely option without flagging it as unclear.

Message: "{message}"
"""

LLM_JUDGE_PROMPT = """A waste picker submitted a scrap sale report that one \
or more automated checks flagged as unusual. Decide whether it's likely a \
legitimate outlier or likely a bad/manipulated report.

Report: {material} -- {quantity} kg sold at {price_per_kg} {currency}/kg in {location}.
Recent price/kg reports for this material in this area: {recent_prices}
What got flagged and why: {flag_reasons}

Legitimate outliers happen -- e.g. heavily contaminated material sells for \
much less, an unusually large or clean batch is a real bulk sale, or a \
picker made an honest reporting mistake with a decimal point. A manipulated \
report usually looks like a suspiciously round number with no plausible \
reason, or fits a pattern with no real-world explanation.
"""


def _recent_prices_for(report: PriceReport) -> List[float]:
    """Trusted price/kg history for this material in this area.

    NOTE (Step 1): market scoping (same currency/country/city pooling)
    is deliberately unchanged here -- a later step will stop pooling
    across incompatible markets. Field names are generic already.
    """
    return [
        r.price_per_kg
        for r in report_repo.trusted_reports()
        if r.material_type == report.material_type
        and r.location.strip().lower() == report.location.strip().lower()
    ]


def _flagged_results(state: PipelineState) -> List[AnomalyVerdict]:
    """Cheap-tier verdicts (deterministic, ml) that came back anomalous, in tier order."""
    return [
        v for v in (state.get("deterministic_result"), state.get("ml_result"))
        if v and v.is_anomalous
    ]


def _finalize(price_report: PriceReport, verdict: AnomalyVerdict, message: str) -> dict:
    """Single place a report is ever written to the trusted store."""
    logger.info(
        "Finalizing pipeline run: is_anomalous=%s, method='%s', message='%s'",
        verdict.is_anomalous,
        verdict.method,
        message,
    )
    if not verdict.is_anomalous:
        report_repo.add(price_report)
    else:
        logger.warning("Report flagged as anomalous by %s check; not storing.", verdict.method)
    _capture_report(price_report, verdict)
    return {
        "verdict": verdict,
        "messages": [{"role": "assistant", "content": message}],
    }


def extract_report(state: PipelineState) -> dict:
    """Single LLM call: raw text -> structured fields."""
    message = state["messages"][-1].content
    logger.info("Extracting report (message length=%d)", len(message))

    prompt = EXTRACTION_PROMPT.format(
        material_list=", ".join(KNOWN_MATERIALS), message=message
    )

    try:
        raw_extraction = _extraction_model().invoke(
            [{"role": "user", "content": prompt}]
        )
        if raw_extraction is None:
            raise ValueError("model returned no structured output (None)")
        logger.info(
            "Extraction succeeded: material=%s quantity_kg=%s total_price=%s currency=%s",
            raw_extraction.material_type,
            raw_extraction.quantity_kg,
            raw_extraction.total_price,
            raw_extraction.currency,
        )
    except Exception:
        logger.exception("Extraction failed, falling back to unclear report")
        raw_extraction = RawExtraction(
            material_type=MaterialType.OTHER,
            material_confidence=0.0,
            quantity_confidence=0.0,
            price_confidence=0.0,
            unclear_fields=["extraction_failed"],
        )

    return {"raw_extraction": raw_extraction}


def validate_and_build(state: PipelineState) -> dict:
    """Deterministic validation: rules, range checks, confidence thresholds."""
    reasons: list[str] = []
    raw = state["raw_extraction"]
    message = state["messages"][-1].content if state.get("messages") else ""

    if raw.quantity_kg is None:
        reasons.append("missing quantity")
    if raw.total_price is None:
        reasons.append("missing price")

    # Structured market fields: explicit LLM extraction wins; the picker's
    # saved settings (context tags) backfill what the message didn't state.
    # Nothing here is guessed -- genuinely missing stays missing.
    tag_city, tag_country = picker_place_from_tags(message)
    tag_currency = picker_currency_from_tags(message)
    tag_neighborhood = picker_neighborhood_from_tags(message)

    currency = normalize_currency(raw.currency or tag_currency)
    country = normalize_place_part(raw.country or tag_country)
    city = normalize_place_part(raw.city or tag_city)
    neighborhood = normalize_place_part(raw.neighborhood or tag_neighborhood)
    reasons.extend(validate_market_fields(currency, country, city, neighborhood))

    price_per_kg = 0.0
    if raw.quantity_kg and raw.total_price:
        price_per_kg = raw.total_price / raw.quantity_kg
        # The sanity bands are denominated in one market's currency. They
        # only apply to that market (or to legacy reports that never named
        # a currency); other explicit currencies skip the band check until
        # per-market bands exist.
        if currency in ("PKR", UNKNOWN_CURRENCY):
            min_price, max_price = PRICE_PER_KG_BANDS[raw.material_type]
            if not (min_price <= price_per_kg <= max_price):
                reasons.append(
                    f"price/kg ({price_per_kg:.0f}) outside expected range "
                    f"for {_material_label(raw.material_type)}"
                )

    if raw.material_type == MaterialType.OTHER:
        reasons.append("material type unclear")

    confidences = {
        "material": raw.material_confidence,
        "quantity": raw.quantity_confidence,
        "price": raw.price_confidence,
    }
    reasons.extend(
        f"low confidence: {field}"
        for field, conf in confidences.items()
        if conf < settings.LOW_CONFIDENCE_THRESHOLD
    )
    reasons.extend(raw.unclear_fields)

    price_report = PriceReport(
        material_type=raw.material_type,
        quantity_kg=raw.quantity_kg or 0.0,
        total_price=raw.total_price or 0.0,
        price_per_kg=round(price_per_kg, 2),
        currency=currency,
        country=country,
        city=city,
        neighborhood=neighborhood,
        location=normalize_location(raw.location_text or neighborhood),
        timestamp=datetime.now(timezone.utc),
        needs_confirmation=bool(reasons),
        confirmation_reason="; ".join(reasons) if reasons else None,
    )

    if price_report.needs_confirmation:
        logger.warning("Report needs confirmation: %s", price_report.confirmation_reason)
        _capture_report(price_report)
    else:
        logger.info(
            "Report validated cleanly: %s %.2fkg @ %.2f %s/kg",
            _material_label(raw.material_type),
            price_report.quantity_kg,
            price_report.price_per_kg,
            price_report.currency,
        )

    return {
        "price_report": price_report,
        "messages": [{
            "role": "assistant",
            "content": (
                f"Report needs confirmation: {price_report.confirmation_reason}"
                if price_report.needs_confirmation
                else f"Report intaken cleanly: {_material_label(raw.material_type)} "
                      f"{price_report.quantity_kg}kg @ {price_report.price_per_kg}/kg"
            ),
        }],
    }


def route_after_validation(state: PipelineState) -> str:
    if state["price_report"].needs_confirmation:
        logger.info("Routing after validation -> 'end' (report needs picker confirmation)")
        return "end"
    logger.info("Routing after validation -> 'deterministic_check'")
    return "deterministic_check"


def deterministic_check_node(state: PipelineState) -> dict:
    price_report = state["price_report"]
    recent = _recent_prices_for(price_report)
    result = anomaly_detector_service.deterministic_check(price_report, recent)
    return {"deterministic_result": result}


def ml_check_node(state: PipelineState) -> dict:
    price_report = state["price_report"]
    recent = _recent_prices_for(price_report)
    median = statistics.median(recent) if recent else 0.0
    result = anomaly_detector_service.ml_check(price_report, median)
    return {"ml_result": result}


def llm_check_node(state: PipelineState) -> dict:
    price_report = state["price_report"]
    recent = _recent_prices_for(price_report)
    flagged = _flagged_results(state)
    flag_reasons = "; ".join(v.reason for v in flagged)

    logger.info("LLM judgment check running: flag_reasons='%s'", flag_reasons)
    prompt = LLM_JUDGE_PROMPT.format(
        material=_material_label(price_report.material_type),
        quantity=price_report.quantity_kg,
        price_per_kg=price_report.price_per_kg,
        currency=price_report.currency,
        location=price_report.location,
        recent_prices=recent,
        flag_reasons=flag_reasons,
    )
    judgment: LLMJudgment = _judge_model().invoke(prompt)
    verdict = AnomalyVerdict(
        is_anomalous=judgment.is_anomalous,
        reason=judgment.reason,
        method="llm",
        confidence=judgment.confidence,
    )
    message = (
        f"LLM review of {_material_label(price_report.material_type)} "
        f"{price_report.quantity_kg}kg @ {price_report.price_per_kg}/kg: "
        + (
            f"flagged as anomalous (confidence {verdict.confidence:.2f}) -- {verdict.reason}"
            if verdict.is_anomalous
            else f"cleared as legitimate -- {verdict.reason}"
        )
    )
    return _finalize(price_report, verdict, message)


def accept_node(state: PipelineState) -> dict:
    price_report = state["price_report"]
    flagged = _flagged_results(state)
    verdict = flagged[-1] if flagged else state["deterministic_result"]
    message = (
        f"Accepted {_material_label(price_report.material_type)} "
        f"{price_report.quantity_kg}kg @ {price_report.price_per_kg}/kg "
        f"via {verdict.method} check -- {verdict.reason}"
    )
    return _finalize(price_report, verdict, message)


def route_after_deterministic(state: PipelineState) -> str:
    price_report = state["price_report"]
    have_enough_history = len(_recent_prices_for(price_report)) >= settings.MIN_REPORTS_FOR_BASELINE
    if anomaly_detector_service.ml_model is not None and have_enough_history:
        logger.info("Routing after deterministic check -> 'ml_check'")
        return "ml_check"
    if settings.USE_LLM_REASONING and state["deterministic_result"].is_anomalous:
        logger.info("Routing after deterministic check -> 'llm_check'")
        return "llm_check"
    logger.info("Routing after deterministic check -> 'accept'")
    return "accept"


def route_after_ml(state: PipelineState) -> str:
    flagged = state["deterministic_result"].is_anomalous or state["ml_result"].is_anomalous
    target = "llm_check" if (settings.USE_LLM_REASONING and flagged) else "accept"
    logger.info("Routing after ML check (flagged=%s) -> '%s'", flagged, target)
    return target


def build_pipeline():
    graph = StateGraph(PipelineState)

    graph.add_node("extract_report", extract_report)
    graph.add_node("validate_and_build", validate_and_build)
    graph.add_node("deterministic_check", deterministic_check_node)
    graph.add_node("ml_check", ml_check_node)
    graph.add_node("llm_check", llm_check_node)
    graph.add_node("accept", accept_node)

    graph.add_edge(START, "extract_report")
    graph.add_edge("extract_report", "validate_and_build")

    graph.add_conditional_edges(
        "validate_and_build",
        route_after_validation,
        {"deterministic_check": "deterministic_check", "end": END},
    )
    graph.add_conditional_edges(
        "deterministic_check",
        route_after_deterministic,
        {"ml_check": "ml_check", "llm_check": "llm_check", "accept": "accept"},
    )
    graph.add_conditional_edges(
        "ml_check",
        route_after_ml,
        {"llm_check": "llm_check", "accept": "accept"},
    )
    graph.add_edge("llm_check", END)
    graph.add_edge("accept", END)

    return graph.compile()


pipeline = build_pipeline()
