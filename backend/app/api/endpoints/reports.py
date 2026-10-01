"""
Reports endpoints: query historical scrap sale reports and log new submissions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.repositories.report_repository import report_repo
from app.schemas.report import (
    MaterialType,
    PriceReport,
    ReportCreate,
    ReportResponse,
    ReportTrustStatus,
)
from app.services.report_trust import mark_accepted, mark_pending
from app.services.location_resolver import (
    UNKNOWN_CURRENCY,
    normalize_currency,
    normalize_location,
    normalize_place_part,
    validate_market_fields,
)
from app.services.anomaly_detector import (
    anomaly_detector_service,
    comparable_prices,
    market_median_for,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=List[ReportResponse])
async def list_reports(
    material: Optional[str] = Query(None, description="Filter by material type"),
    location: Optional[str] = Query(None, description="Filter by neighborhood/location"),
    trusted_only: bool = Query(True, description="Only return reports that passed validation without confirmation"),
):
    """
    List historical price reports with optional filtering by material, location, and validation status.
    """
    if material:
        try:
            mat_enum = MaterialType(material.strip().lower())
            reports = report_repo.find_by_material_and_location(mat_enum, location, trusted_only=trusted_only)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid material type '{material}'.")
    elif location:
        all_reps = report_repo.trusted_reports() if trusted_only else report_repo.all_reports()
        normalized = normalize_location(location)
        reports = [r for r in all_reps if normalize_location(r.location) == normalized]
    else:
        reports = report_repo.trusted_reports() if trusted_only else report_repo.all_reports()

    return reports


@router.post("", response_model=ReportResponse, status_code=201)
async def create_report(payload: ReportCreate):
    """
    Directly log a validated scrap sale report into the system.
    """
    price_per_kg = payload.total_price / payload.quantity_kg
    currency = normalize_currency(payload.currency)
    country = normalize_place_part(payload.country)
    city = normalize_place_part(payload.city)
    neighborhood = normalize_place_part(payload.neighborhood)

    reasons: list[str] = validate_market_fields(currency, country, city, neighborhood)

    # Single source of truth is ``settings.price_band_for`` (verified
    # Pakistan/PKR). Raw-config fallback preserves legacy PKR/unknown
    # behavior exactly; other explicit currencies skip the check.
    if currency in ("PKR", UNKNOWN_CURRENCY):
        band = settings.price_band_for(
            payload.material_type, country, currency
        ) or settings.PRICE_PER_KG_BANDS.get(
            payload.material_type.value, (5.0, 500.0)
        )
        min_band, max_band = band
        if not (min_band <= price_per_kg <= max_band):
            reasons.append(
                f"Price per kg ({price_per_kg:.1f}) outside sanity range "
                f"[{min_band}, {max_band}]"
            )

    # Explicit API values take precedence over any defaults -- never
    # overwrite them. The legacy `location` stays as the raw compatible
    # label; structured fields remain authoritative for the estimator.
    raw_location = (payload.location or "").strip()
    if not raw_location or raw_location.lower() == "unknown":
        raw_location = neighborhood or "unknown"
    # Step 8: canonical trust state is explicit from intake. Validation
    # failures start as PENDING (never silently ACCEPTED); the validator
    # keeps needs_confirmation in sync so no contradictory state exists.
    report = PriceReport(
        material_type=payload.material_type,
        quantity_kg=payload.quantity_kg,
        total_price=payload.total_price,
        price_per_kg=round(price_per_kg, 2),
        currency=currency,
        country=country,
        city=city,
        neighborhood=neighborhood,
        location=normalize_location(raw_location),
        timestamp=datetime.now(timezone.utc),
        trust_status=ReportTrustStatus.PENDING if reasons else ReportTrustStatus.ACCEPTED,
        needs_confirmation=bool(reasons),
        confirmation_reason="; ".join(reasons) if reasons else None,
        picker_id=payload.picker_id,
    )

    # Step 4: anomaly populations are market/location scoped (same material
    # + same market, tightest location scope with data) -- never pooled
    # across incompatible markets or across cities for a local baseline.
    # Step 8: history is ACCEPTED + fresh only (canonical trust + Step 7
    # freshness inside comparable_*). The current report is evaluated
    # against trusted history BEFORE it is persisted, so it never anchors
    # its own baseline.
    trusted = report_repo.trusted_reports()
    recent_prices = comparable_prices(report, trusted)
    verdict = anomaly_detector_service.deterministic_check(report, recent_prices)

    if not verdict.is_anomalous and anomaly_detector_service.ml_model is not None:
        if len(recent_prices) >= settings.MIN_REPORTS_FOR_BASELINE:
            median = market_median_for(report, trusted)
            verdict = anomaly_detector_service.ml_check(report, median)

    if reasons or verdict.is_anomalous:
        # Flagged -> PENDING: persisted for review, NEVER market data.
        # Validation reasons and anomaly evidence are both preserved.
        parts: list[str] = []
        if reasons:
            parts.append("; ".join(reasons))
        if verdict.is_anomalous:
            parts.append(f"{verdict.method} anomaly check: {verdict.reason}")
        report = mark_pending(report, "; ".join(parts))
        report_repo.add(report)
        logger.warning(
            "REST report held for review as PENDING: material=%s location=%s reason=%s",
            report.material_type,
            report.location,
            report.confirmation_reason,
        )
    else:
        # Normal -> ACCEPTED: eligible for estimator + anomaly history.
        report = mark_accepted(report)
        report_repo.add(report)

    return report
