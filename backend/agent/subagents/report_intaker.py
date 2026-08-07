"""
Report-to-verdict pipeline for ScrapSense

it's a single graph:

    START -> extract_report -> validate_and_build --+--> deterministic_check --+--> ml_check --+--> llm_check --> END
                                                      |                        |                |
                                                      | (needs_confirmation)   |                +----------------+--> accept --> END
                                                      v                        |
                                                     END                       +---------------------------------> accept --> END

If intake flags the report for picker confirmation (missing/unclear fields,
low confidence, price outside its sanity band), the graph stops there --
there's no point running anomaly detection against numbers that aren't
trustworthy yet. Only a cleanly-validated report moves on to the
deterministic / ML / LLM anomaly tiers, the three-tier logic.

"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import statistics
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, START, END, MessagesState
from langchain.chat_models import init_chat_model
from deepagents import CompiledSubAgent

from schemas.report import MaterialType, RawExtraction, PriceReport, LLMJudgment, AnomalyVerdict
from ml_anomaly_model import ml_score, load_ml_model, train_ml_model
import db_store as store

from dotenv import load_dotenv
load_dotenv()


logger = logging.getLogger(__name__)


# --- load ML model ----
ml_model = load_ml_model()


# ---- reports fetched from DB ----
def _trusted_reports() -> list[PriceReport]:
    return [r for r in store.all_reports() if not r.needs_confirmation]


# ----- retrain the model -----
def retrain() -> bool:
    global ml_model
    trusted = _trusted_reports()
    prices_by_material: dict = defaultdict(list)
    for r in trusted:
        prices_by_material[r.material_type].append(r.price_paid_pkr_per_kg)
    medians = {m: statistics.median(p) for m, p in prices_by_material.items()}
    records = [
        {
            "price_paid_pkr_per_kg": r.price_paid_pkr_per_kg,
            "quantity_kg": r.quantity_kg,
            "material_median": medians.get(r.material_type, r.price_paid_pkr_per_kg),
        }
        for r in trusted
    ]
    model = train_ml_model(records)
    if model:
        ml_model = model
    return model is not None

# ------
# config
# ------

KNOWN_MATERIALS = [m.value for m in MaterialType]

# Sanity price/kg bands (PKR), per material. Anything outside its band gets
# flagged, not rejected -- could be legitimate (e.g. rare metal) but needs a
# human look. NOTE: placeholder ranges -- swap in real regional pricing data.

PRICE_PER_KG_BANDS: dict[MaterialType, tuple[float, float]] = {
    MaterialType.PLASTIC_PET: (20, 200),
    MaterialType.PLASTIC_HDPE: (15, 150),
    MaterialType.GLASS: (2, 20),
    MaterialType.METAL_ALUMINUM: (150, 1500),
    MaterialType.METAL_STEEL: (30, 200),
    MaterialType.CARDBOARD: (5, 40),
    MaterialType.MIXED_PAPER: (5, 30),
    MaterialType.OTHER: (5, 500),  # material unknown -- wide catch-all
}

LOW_CONFIDENCE_THRESHOLD = 0.6

# ---- anomaly-tier thresholds -----

USE_LLM_REASONING = True
LOW_RATIO = 0.5
HIGH_RATIO = 2.0
MIN_REPORTS_FOR_BASELINE = 3  # need at least this many recent reports to judge


# -----
# model
# -----

gemini_model = init_chat_model("google_genai:gemini-3.6-flash")
_structured_extraction_model = gemini_model.with_structured_output(RawExtraction)
_structured_llm_judge = gemini_model.with_structured_output(LLMJudgment)


# -----------
# graph state
# -----------

class PipelineState(MessagesState):
    raw_extraction: RawExtraction
    price_report: PriceReport

    # anomaly-tier inputs / scratch
    deterministic_result: Optional[AnomalyVerdict]
    ml_result: Optional[AnomalyVerdict]
    verdict: Optional[AnomalyVerdict]   # final output, set by llm_check or accept




# ------------
# intake nodes
# ------------


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


# ------- node 1 -------

def extract_report(state: PipelineState) -> dict:
    """Single LLM call: raw text -> structured (but not yet validated) fields."""

    message = state["messages"][-1].content
    logger.info("Extracting report (message length=%d)", len(message))

    prompt = EXTRACTION_PROMPT.format(
        material_list=", ".join(KNOWN_MATERIALS), message=message
    )

    try:
        raw_extraction = _structured_extraction_model.invoke(
            [{"role": "user", "content": prompt}]
        )
        if raw_extraction is None:
            raise ValueError("model returned no structured output (None)")
        logger.info(
            "Extraction succeeded: material=%s quantity_kg=%s price_paid_pkr=%s",
            raw_extraction.material_type,
            raw_extraction.quantity_kg,
            raw_extraction.price_paid_pkr,
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


# ------ node 2 --------

def validate_and_build(state: PipelineState) -> dict:
    """Deterministic pass: no LLM call. Just rules and arithmetic."""
    reasons: list[str] = []
    raw = state["raw_extraction"]

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
        needs_confirmation=bool(reasons),
        confirmation_reason="; ".join(reasons) if reasons else None,
    )

    if price_report.needs_confirmation:
        logger.warning("Report needs confirmation: %s", price_report.confirmation_reason)
    else:
        logger.info(
            "Report validated cleanly: %s %.2fkg @ %.2f/kg",
            raw.material_type.value,
            price_report.quantity_kg,
            price_report.price_paid_pkr_per_kg,
        )

    return {
        "price_report": price_report,
        "messages": [{
            "role": "assistant",
            "content": (
                f"Report needs confirmation: {price_report.confirmation_reason}"
                if price_report.needs_confirmation
                else f"Report intaken cleanly: {raw.material_type.value} "
                     f"{price_report.quantity_kg}kg @ {price_report.price_paid_pkr_per_kg}/kg"
            ),
        }],
    }


def route_after_validation(state: PipelineState) -> str:
    """Only score for anomalies once a report is trustworthy. A report that
    needs picker confirmation doesn't have numbers worth checking yet."""
    if state["price_report"].needs_confirmation:
        logger.info("Routing after validation -> 'end' (report needs picker confirmation)")
        return "end"
    logger.info("Routing after validation -> 'deterministic_check'")
    return "deterministic_check"


# ----------------
# anomaly-tier checks
# ----------------


def _deterministic_check(
    report: PriceReport, recent_prices_per_kg: list[float]
) -> AnomalyVerdict:

    logger.info(
        "Deterministic check running for %s @ %.2f PKR/kg (history count=%d)",
        report.material_type.value,
        report.price_paid_pkr_per_kg,
        len(recent_prices_per_kg),
    )
    if len(recent_prices_per_kg) < MIN_REPORTS_FOR_BASELINE:
        verdict = AnomalyVerdict(
            is_anomalous=False,
            reason="not enough regional history yet -- accepted by default",
            method="deterministic",
        )
        logger.info("Deterministic check result: %s", verdict)
        return verdict

    median = statistics.median(recent_prices_per_kg)
    price = report.price_paid_pkr_per_kg

    if price < median * LOW_RATIO:
        verdict = AnomalyVerdict(
            is_anomalous=True,
            reason=f"price/kg ({price:.0f}) is under half the recent median ({median:.0f})",
            method="deterministic",
        )
    elif price > median * HIGH_RATIO:
        verdict = AnomalyVerdict(
            is_anomalous=True,
            reason=f"price/kg ({price:.0f}) is over double the recent median ({median:.0f})",
            method="deterministic",
        )
    else:
        verdict = AnomalyVerdict(
            is_anomalous=False,
            reason=f"within normal range of recent median ({median:.0f})",
            method="deterministic",
        )
    logger.info("Deterministic check result: %s", verdict)
    return verdict


def _ml_check(report: PriceReport, ml_model, material_median: float) -> AnomalyVerdict:
    logger.info("ML check running for %s with median=%.2f", report.material_type.value, material_median)
    is_anom, raw_score = ml_score(
        ml_model, report.price_paid_pkr_per_kg, report.quantity_kg, material_median
    )

    verdict = AnomalyVerdict(
        is_anomalous=is_anom,
        reason=f"isolation forest flagged this price/quantity combination (score {raw_score:.3f})",
        method="ml",
        confidence=min(1.0, abs(raw_score) * 2),
    )
    logger.info("ML check result: %s", verdict)
    return verdict


LLM_JUDGE_PROMPT = """A waste picker submitted a scrap sale report that one \
or more automated checks flagged as unusual. Decide whether it's likely a \
legitimate outlier or likely a bad/manipulated report.

Report: {material} -- {quantity} kg sold at {price_per_kg} PKR/kg in {location}.
Recent price/kg reports for this material in this area: {recent_prices}
What got flagged and why: {flag_reasons}

Legitimate outliers happen -- e.g. heavily contaminated material sells for \
much less, an unusually large or clean batch is a real bulk sale, or a \
picker made an honest reporting mistake with a decimal point. A manipulated \
report usually looks like a suspiciously round number with no plausible \
reason, or fits a pattern with no real-world explanation.
"""


def _llm_check(
    report: PriceReport, recent_prices_per_kg: list[float], flag_reasons: str
) -> AnomalyVerdict:
    logger.info("LLM judgment check running: flag_reasons='%s'", flag_reasons)
    prompt = LLM_JUDGE_PROMPT.format(
        material=report.material_type.value,
        quantity=report.quantity_kg,
        price_per_kg=report.price_paid_pkr_per_kg,
        location=report.location,
        recent_prices=recent_prices_per_kg,
        flag_reasons=flag_reasons,
    )
    judgment: LLMJudgment = _structured_llm_judge.invoke(prompt)
    verdict = AnomalyVerdict(
        is_anomalous=judgment.is_anomalous,
        reason=judgment.reason,
        method="llm",
        confidence=judgment.confidence,
    )
    logger.info("LLM judgment check result: %s", verdict)
    return verdict

# ----------------------------
# shared helpers (dedup'd bits)
# ----------------------------

def _recent_prices_for(report: PriceReport) -> list[float]:
    """Trusted price/kg history for this material in this area."""
    return [
        r.price_paid_pkr_per_kg
        for r in _trusted_reports()
        if r.material_type == report.material_type
        and r.location.lower() == report.location.lower()
    ]


def _flagged_results(state: PipelineState) -> list[AnomalyVerdict]:
    """Cheap-tier verdicts (deterministic, ml) that came back anomalous, in tier order."""
    return [
        v for v in (state.get("deterministic_result"), state.get("ml_result"))
        if v and v.is_anomalous
    ]


def _finalize(price_report: PriceReport, verdict: AnomalyVerdict, message: str) -> dict:
    """Single place a report is ever written to the trusted store -- only once
    the pipeline has reached its actual terminal verdict, never at an
    intermediate tier that might still get overridden by a later tier."""
    logger.info(
        "Finalizing pipeline run: is_anomalous=%s, method='%s', message='%s'",
        verdict.is_anomalous,
        verdict.method,
        message,
    )
    if not verdict.is_anomalous:
        store.add(price_report)
    else:
        logger.warning("Report flagged as anomalous by %s check; not storing.", verdict.method)
    return {
        "verdict": verdict,
        "messages": [{"role": "assistant", "content": message}],
    }


# ------------------
# anomaly-tier nodes
# ------------------

# ----- node 1 -----

def deterministic_check_node(state: PipelineState) -> dict:
    price_report = state["price_report"]
    recent = _recent_prices_for(price_report)
    result = _deterministic_check(price_report, recent)
    return {"deterministic_result": result}



# ----- node 2 -----

def ml_check_node(state: PipelineState) -> dict:
    price_report = state["price_report"]
    recent = _recent_prices_for(price_report)
    median = statistics.median(recent) if recent else 0.0
    result = _ml_check(price_report, ml_model, median)
    return {"ml_result": result}



# ----- node 3 -----

def llm_check_node(state: PipelineState) -> dict:
    price_report = state["price_report"]
    recent = _recent_prices_for(price_report)
    flagged = _flagged_results(state)
    flag_reasons = "; ".join(v.reason for v in flagged)
    verdict = _llm_check(price_report, recent, flag_reasons)
    message = (
        f"LLM review of {price_report.material_type.value} "
        f"{price_report.quantity_kg}kg @ {price_report.price_paid_pkr_per_kg}/kg: "
        + (
            f"flagged as anomalous (confidence {verdict.confidence:.2f}) -- {verdict.reason}"
            if verdict.is_anomalous
            else f"cleared as legitimate -- {verdict.reason}"
        )
    )
    return _finalize(price_report, verdict, message)


# --------- node 4 ----------

def accept_node(state: PipelineState) -> dict:
    """Neither cheap check flagged it, or USE_LLM_REASONING is off --
    resolve straight to the strongest cheap-tier result."""
    price_report = state["price_report"]
    flagged = _flagged_results(state)
    verdict = flagged[-1] if flagged else state["deterministic_result"]  # prefer ML verdict if both flagged
    message = (
        f"Accepted {price_report.material_type.value} "
        f"{price_report.quantity_kg}kg @ {price_report.price_paid_pkr_per_kg}/kg "
        f"via {verdict.method} check -- {verdict.reason}"
    )
    return _finalize(price_report, verdict, message)


def route_after_deterministic(state: PipelineState) -> str:
    price_report = state["price_report"]
    have_enough_history = len(_recent_prices_for(price_report)) >= MIN_REPORTS_FOR_BASELINE
    if ml_model is not None and have_enough_history:
        logger.info("Routing after deterministic check -> 'ml_check'")
        return "ml_check"
    if USE_LLM_REASONING and state["deterministic_result"].is_anomalous:
        logger.info("Routing after deterministic check -> 'llm_check'")
        return "llm_check"
    logger.info("Routing after deterministic check -> 'accept'")
    return "accept"


def route_after_ml(state: PipelineState) -> str:
    flagged = state["deterministic_result"].is_anomalous or state["ml_result"].is_anomalous
    target = "llm_check" if (USE_LLM_REASONING and flagged) else "accept"
    logger.info("Routing after ML check (flagged=%s) -> '%s'", flagged, target)
    return target



# ------------
#  build graph
# ------------

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

# ------ subagent ------

scrap_pipeline_agent = CompiledSubAgent(
    name="scrap_report_pipeline",
    description=(
        "Takes a picker's raw sale message and returns a validated price "
        "report plus an anomaly verdict, in one call. Flags reports that "
        "need the picker's confirmation instead of guessing."
    ),
    runnable=pipeline,
)