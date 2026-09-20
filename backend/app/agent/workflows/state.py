"""
State schema for the report intake and anomaly pipeline workflow.
"""

from __future__ import annotations

from typing import Optional
from langgraph.graph import MessagesState

from app.schemas.report import AnomalyVerdict, PriceReport, RawExtraction


class PipelineState(MessagesState):
    raw_extraction: RawExtraction
    price_report: PriceReport

    # Anomaly-tier inputs / scratch
    deterministic_result: Optional[AnomalyVerdict]
    ml_result: Optional[AnomalyVerdict]
    verdict: Optional[AnomalyVerdict]
