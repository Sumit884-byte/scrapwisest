"""
Orchestrator for ScrapSense.

Routes two request types:
  - "report"  : picker submits a sale → intake → anomaly check → store
  - "query"   : picker asks what something is worth → price estimate
"""

from __future__ import annotations

import statistics as _stats
from collections import defaultdict

from app.backend.agent_schemas.report import MaterialType, PriceReport
from agents.report_intake import process_report
from agents.anomaly_detect import check_anomaly
from agents.price_estimator import estimate, PriceEstimate
from app.backend.ml_anomaly_model import load as load_ml_model, train as train_ml_model
import app.backend.store as store

_ml_model = load_ml_model()


def _trusted_reports() -> list[PriceReport]:
    return [r for r in store.all_reports() if not r.needs_confirmation]


def retrain() -> bool:
    global _ml_model
    trusted = _trusted_reports()
    prices_by_material: dict = defaultdict(list)
    for r in trusted:
        prices_by_material[r.material_type].append(r.price_paid_pkr_per_kg)
    medians = {m: _stats.median(p) for m, p in prices_by_material.items()}
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
        _ml_model = model
    return model is not None


def submit_report(message: str, reported_by: str) -> dict:
    price_report = process_report(message, reported_by)

    if price_report.needs_confirmation:
        return {
            "accepted": False,
            "needs_confirmation": True,
            "confirmation_reason": price_report.confirmation_reason,
            "report": price_report,
        }

    recent = [
        r.price_paid_pkr_per_kg
        for r in _trusted_reports()
        if r.material_type == price_report.material_type
        and r.location.lower() == price_report.location.lower()
    ]

    verdict = check_anomaly(price_report, recent, _ml_model)

    if not verdict.is_anomalous:
        store.add(price_report)
        return {"accepted": True, "verdict": verdict, "report": price_report}

    return {
        "accepted": False,
        "needs_confirmation": False,
        "anomaly_verdict": verdict,
        "report": price_report,
    }


def query_price(material_str: str, location: str) -> PriceEstimate | dict:
    try:
        material = MaterialType(material_str.lower())
    except ValueError:
        return {"error": f"unknown material '{material_str}'. Known: {[m.value for m in MaterialType]}"}

    return estimate(material, location, _trusted_reports())
