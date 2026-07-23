"""
Anomaly agent for ScrapSense -- v3, now wired up as a LangGraph graph
instead of one big function. Same three signals as before:

  1. Deterministic  -- price/kg vs. recent median. Always runs.
  2. ML              -- Isolation Forest over (price_ratio, quantity).
                        Runs only if a trained model was passed in and
                        there's enough regional history.
  3. LLM              -- only runs if (1) or (2) flagged something. Makes
                        the human-readable judgment call.

Graph shape:

    START -> deterministic_check --+--> ml_check --+--> llm_check --> END
                                    |                |
                                    +----------------+--> accept --> END

  * deterministic_check -> ml_check only if ml_model is available and
    there's enough history (same condition check_anomaly() used to gate on).
  * either branch -> llm_check only if something got flagged AND
    USE_LLM_REASONING is on; otherwise -> accept.

Pass ml_model=None in the initial state to skip tier 2 entirely (e.g.
before ml_anomaly_model.train() has enough data).
"""

from __future__ import annotations

import statistics
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from agent_schemas.report import PriceReport
from ml_anomaly_model import score as ml_score

from chat_model import gemini_model

# ---------------------------------------------------------------------------
# TOGGLE
# ---------------------------------------------------------------------------
USE_LLM_REASONING = True

# Deterministic thresholds
LOW_RATIO = 0.5
HIGH_RATIO = 2.0
MIN_REPORTS_FOR_BASELINE = 3  # need at least this many recent reports to judge


class AnomalyVerdict(BaseModel):
    is_anomalous: bool
    reason: str
    method: str  # "deterministic" | "ml" | "llm"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class LLMJudgment(BaseModel):
    """Schema the LLM judge fills in -- method/method-specific fields get
    added back on by _llm_check() once we have this."""
    is_anomalous: bool
    reason: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)


class AnomalyState(TypedDict):
    price_report: PriceReport
    recent_prices_per_kg: list[float]
    ml_model: Optional[object]          # IsolationForest, or None to skip tier 2
    deterministic_result: Optional[AnomalyVerdict]
    ml_result: Optional[AnomalyVerdict]
    verdict: Optional[AnomalyVerdict]   # final output, set by llm_check or accept


# ---------------------------------------------------------------------------
# CHEAP-TIER CHECKS (unchanged logic -- reused by both the graph nodes below
# and compare_modes() for eval)
# ---------------------------------------------------------------------------

def _deterministic_check(
    report: PriceReport, recent_prices_per_kg: list[float]
) -> AnomalyVerdict:
    if len(recent_prices_per_kg) < MIN_REPORTS_FOR_BASELINE:
        return AnomalyVerdict(
            is_anomalous=False,
            reason="not enough regional history yet -- accepted by default",
            method="deterministic",
        )

    median = statistics.median(recent_prices_per_kg)
    price = report.price_paid_pkr_per_kg

    if price < median * LOW_RATIO:
        return AnomalyVerdict(
            is_anomalous=True,
            reason=f"price/kg ({price:.0f}) is under half the recent median ({median:.0f})",
            method="deterministic",
        )
    if price > median * HIGH_RATIO:
        return AnomalyVerdict(
            is_anomalous=True,
            reason=f"price/kg ({price:.0f}) is over double the recent median ({median:.0f})",
            method="deterministic",
        )
    return AnomalyVerdict(
        is_anomalous=False,
        reason=f"within normal range of recent median ({median:.0f})",
        method="deterministic",
    )


def _ml_check(
    report: PriceReport, ml_model, material_median: float
) -> AnomalyVerdict:
    is_anom, raw_score = ml_score(
        ml_model, report.price_paid_pkr_per_kg, report.quantity_kg, material_median
    )
    return AnomalyVerdict(
        is_anomalous=is_anom,
        reason=f"isolation forest flagged this price/quantity combination (score {raw_score:.3f})",
        method="ml",
        confidence=min(1.0, abs(raw_score) * 2),
    )


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

_structured_llm_judge = gemini_model.with_structured_output(LLMJudgment)


def _llm_check(
    report: PriceReport,
    recent_prices_per_kg: list[float],
    flag_reasons: str,
) -> AnomalyVerdict:
    prompt = LLM_JUDGE_PROMPT.format(
        material=report.material_type.value,
        quantity=report.quantity_kg,
        price_per_kg=report.price_paid_pkr_per_kg,
        location=report.location,
        recent_prices=recent_prices_per_kg,
        flag_reasons=flag_reasons,
    )
    judgment: LLMJudgment = _structured_llm_judge.invoke(prompt)
    return AnomalyVerdict(
        is_anomalous=judgment.is_anomalous,
        reason=judgment.reason,
        method="llm",
        confidence=judgment.confidence,
    )


# ---------------------------------------------------------------------------
# GRAPH NODES
# ---------------------------------------------------------------------------

def deterministic_check_node(state: AnomalyState) -> dict:
    result = _deterministic_check(state["price_report"], state["recent_prices_per_kg"])
    return {"deterministic_result": result}


def ml_check_node(state: AnomalyState) -> dict:
    median = statistics.median(state["recent_prices_per_kg"])
    result = _ml_check(state["price_report"], state["ml_model"], median)
    return {"ml_result": result}


def llm_check_node(state: AnomalyState) -> dict:
    flagged = [
        v for v in (state.get("deterministic_result"), state.get("ml_result"))
        if v and v.is_anomalous
    ]
    flag_reasons = "; ".join(v.reason for v in flagged)
    verdict = _llm_check(state["price_report"], state["recent_prices_per_kg"], flag_reasons)
    return {"verdict": verdict}


def accept_node(state: AnomalyState) -> dict:
    """Neither cheap check flagged it, or USE_LLM_REASONING is off --
    resolve straight to the strongest cheap-tier result."""
    flagged = [
        v for v in (state.get("deterministic_result"), state.get("ml_result"))
        if v and v.is_anomalous
    ]
    verdict = flagged[-1] if flagged else state["deterministic_result"]  # prefer ML verdict if both flagged
    return {"verdict": verdict}


# ---------------------------------------------------------------------------
# ROUTING
# ---------------------------------------------------------------------------

def route_after_deterministic(state: AnomalyState) -> str:
    ml_model = state.get("ml_model")
    have_enough_history = len(state["recent_prices_per_kg"]) >= MIN_REPORTS_FOR_BASELINE
    if ml_model is not None and have_enough_history:
        return "ml_check"
    if USE_LLM_REASONING and state["deterministic_result"].is_anomalous:
        return "llm_check"
    return "accept"


def route_after_ml(state: AnomalyState) -> str:
    flagged = state["deterministic_result"].is_anomalous or state["ml_result"].is_anomalous
    return "llm_check" if (USE_LLM_REASONING and flagged) else "accept"


# ---------------------------------------------------------------------------
# GRAPH ASSEMBLY
# ---------------------------------------------------------------------------

def build_anomaly_graph():
    graph = StateGraph(AnomalyState)

    graph.add_node("deterministic_check", deterministic_check_node)
    graph.add_node("ml_check", ml_check_node)
    graph.add_node("llm_check", llm_check_node)
    graph.add_node("accept", accept_node)

    graph.set_entry_point("deterministic_check")

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


anomaly_graph = build_anomaly_graph()


def check_anomaly(
    price_report: PriceReport,
    recent_prices_per_kg: list[float],
    ml_model=None,
) -> AnomalyVerdict:
    """Entry point the orchestrator calls -- same signature as before,
    now backed by the graph. Pass ml_model=None to skip the ML tier."""
    result = anomaly_graph.invoke(
        {
            "price_report": price_report,
            "recent_prices_per_kg": recent_prices_per_kg,
            "ml_model": ml_model,
            "deterministic_result": None,
            "ml_result": None,
            "verdict": None,
        }
    )
    return result["verdict"]


# ---------------------------------------------------------------------------
# EVAL HELPER (unchanged -- doesn't run through the graph, just runs every
# tier and returns them side by side)
# ---------------------------------------------------------------------------

def compare_modes(
    report: PriceReport,
    recent_prices_per_kg: list[float],
    ml_model=None,
) -> dict[str, AnomalyVerdict]:
    results: dict[str, AnomalyVerdict] = {
        "deterministic": _deterministic_check(report, recent_prices_per_kg)
    }
    if ml_model is not None and len(recent_prices_per_kg) >= MIN_REPORTS_FOR_BASELINE:
        median = statistics.median(recent_prices_per_kg)
        results["ml"] = _ml_check(report, ml_model, median)

    flagged = [v for v in results.values() if v.is_anomalous]
    if flagged:
        combined_reason = "; ".join(v.reason for v in flagged)
        results["llm"] = _llm_check(report, recent_prices_per_kg, combined_reason)

    return results