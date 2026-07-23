"""
Report-intake agent for ScrapSense.

Job: turn a picker's raw message (text, or transcribed voice) into a
validated PriceReport. Never silently guesses on unclear fields --
flags them for the picker to confirm instead.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, TypedDict

from pydantic import BaseModel, Field
from chat_model import gemini_model

from langgraph.graph import StateGraph, START, END

logger = logging.getLogger(__name__)


from agent_schemas.report import RawExtraction, PriceReport, MaterialType

KNOWN_MATERIALS = [m.value for m in MaterialType]

# Sanity price/kg bands (PKR), per material. Anything outside its band gets
# flagged, not rejected -- could be legitimate (e.g. rare metal) but needs a
# human look. NOTE: placeholder ranges -- swap in real regional pricing data.
PRICE_PER_KG_BANDS: dict[MaterialType, tuple[float, float]] = {
    MaterialType.PLASTIC_PET: (20, 200),
    MaterialType.PLASTIC_HDPE: (15, 150),
    MaterialType.GLASS: (2, 20),
    MaterialType.METAL_ALUMINUM: (150, 500),
    MaterialType.METAL_STEEL: (30, 200),
    MaterialType.CARDBOARD: (5, 40),
    MaterialType.MIXED_PAPER: (5, 30),
    MaterialType.OTHER: (5, 500),  # material unknown -- wide catch-all
}

LOW_CONFIDENCE_THRESHOLD = 0.6


class ReportState(TypedDict):
    message: str
    raw_extraction: RawExtraction
    reported_by: str
    price_report: PriceReport


EXTRACTION_PROMPT = """You are extracting a scrap sale report from a waste \
picker's message. The message may be in English, Urdu, or Roman Urdu, and \
may contain informal phrasing or speech-to-text errors.
 
Extract these fields:
- material_type: must be exactly one of {material_list}. If genuinely \
unclear, use "other".
- quantity_kg: weight sold, in kilograms. Convert if given in another unit.
- price_paid_pkr: TOTAL price paid in Pakistani Rupees (not per-kg, unless \
that's explicitly how it was stated -- then multiply it out).
- location_text: neighborhood or area name mentioned, if any.
 
For each field, give a confidence score from 0 to 1. If you are genuinely \
guessing (an ambiguous number, an unclear material), add that field's name \
to unclear_fields and lower its confidence. Do not silently pick the most \
likely option without flagging it as unclear.
 
Message: "{message}"
"""


def extract_report(state: ReportState):
    """Single LLM call: raw text -> structured (but not yet validated) fields."""

    message = state["message"]
    reported_by = state["reported_by"]
    logger.info(
        "Extracting report for %s (message length=%d)", reported_by, len(message)
    )

    prompt = EXTRACTION_PROMPT.format(
        material_list=", ".join(KNOWN_MATERIALS), message=message
    )

    structured_model = gemini_model.with_structured_output(RawExtraction)
    try:
        raw_extraction = structured_model.invoke([{"role": "user", "content": prompt}])
        if raw_extraction is None:
            raise ValueError("model returned no structured output (None)")
        logger.debug(
            "Extraction succeeded for %s: material=%s quantity_kg=%s price_paid_pkr=%s",
            reported_by,
            raw_extraction.material_type,
            raw_extraction.quantity_kg,
            raw_extraction.price_paid_pkr,
        )
    except Exception:
        logger.exception(
            "Extraction failed for %s, falling back to unclear report", reported_by
        )
        raw_extraction = RawExtraction(
            material_type=MaterialType.OTHER,
            material_confidence=0.0,
            quantity_confidence=0.0,
            price_confidence=0.0,
            unclear_fields=["extraction_failed"],
        )

    return {"raw_extraction": raw_extraction}


def validate_and_build(state: ReportState):
    """Deterministic pass: no LLM call. Just rules and arithmetic."""
    reasons: list[str] = []

    raw = state["raw_extraction"]
    reported_by = state["reported_by"]

    if raw.quantity_kg is None:
        reasons.append("missing quantity")
    if raw.price_paid_pkr is None:
        reasons.append("missing price")

    price_per_kg = 0.0
    if raw.quantity_kg and raw.price_paid_pkr:
        price_per_kg = raw.price_paid_pkr / raw.quantity_kg
        min_price, max_price = PRICE_PER_KG_BANDS[raw.material_type]
        if not (min_price <= price_per_kg <= max_price):
            reasons.append(
                f"price/kg ({price_per_kg:.0f}) outside expected range "
                f"for {raw.material_type.value}"
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
        if conf < LOW_CONFIDENCE_THRESHOLD
    )
    reasons.extend(raw.unclear_fields)

    price_report = PriceReport(
        material_type=raw.material_type,
        quantity_kg=raw.quantity_kg or 0.0,
        price_paid_pkr=raw.price_paid_pkr or 0.0,
        price_paid_pkr_per_kg=round(price_per_kg, 2),
        location=raw.location_text or "unknown",
        timestamp=datetime.now(timezone.utc),
        reported_by=reported_by,
        needs_confirmation=bool(reasons),
        confirmation_reason="; ".join(reasons) if reasons else None,
    )

    # Same rule as above: wrap in a state-update dict.
    if price_report.needs_confirmation:
        logger.warning(
            "Report from %s needs confirmation: %s",
            reported_by,
            price_report.confirmation_reason,
        )
    else:
        logger.info(
            "Report from %s validated cleanly: %s %.2fkg @ %.2f/kg",
            reported_by,
            raw.material_type.value,
            price_report.quantity_kg,
            price_report.price_paid_pkr_per_kg,
        )

    return {"price_report": price_report}


# Build workflow
agent_builder = StateGraph(ReportState)

# Add nodes
agent_builder.add_node("extract_report", extract_report)
agent_builder.add_node("validate_and_build", validate_and_build)

# Add edges to connect nodes
agent_builder.add_edge(START, "extract_report")
agent_builder.add_edge("extract_report", "validate_and_build")
agent_builder.add_edge("validate_and_build", END)

# Compile the agent
agent = agent_builder.compile()


def process_report(message: str, reported_by: str) -> PriceReport:
    """Entry point the orchestrator (and tests) call."""
    result = agent.invoke({"message": message, "reported_by": reported_by})
    return result["price_report"]


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    demo_report = process_report(
        "sold two kilo plastic for three hundred near income colony", "tayyab"
    )
    print(demo_report)