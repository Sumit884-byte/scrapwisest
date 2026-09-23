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
from app.schemas.report import MaterialType, PriceReport, ReportCreate, ReportResponse
from app.services.location_resolver import (
    UNKNOWN_CURRENCY,
    normalize_currency,
    normalize_location,
    normalize_place_part,
    validate_market_fields,
)
from app.services.anomaly_detector import anomaly_detector_service

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

    # The sanity bands are denominated in one market's currency. They only
    # apply to that market (or to legacy reports that never named a
    # currency); other explicit currencies skip the band check until
    # per-market bands exist.
    if currency in ("PKR", UNKNOWN_CURRENCY):
        min_band, max_band = settings.PRICE_PER_KG_BANDS.get(
            payload.material_type.value, (5.0, 500.0)
        )
        if not (min_band <= price_per_kg <= max_band):
            reasons.append(
                f"Price per kg ({price_per_kg:.1f}) outside sanity range "
                f"[{min_band}, {max_band}]"
            )

    report = PriceReport(
        material_type=payload.material_type,
        quantity_kg=payload.quantity_kg,
        total_price=payload.total_price,
        price_per_kg=round(price_per_kg, 2),
        currency=currency,
        country=country,
        city=city,
        neighborhood=neighborhood,
        location=normalize_location(payload.location or neighborhood),
        timestamp=datetime.now(timezone.utc),
        needs_confirmation=bool(reasons),
        confirmation_reason="; ".join(reasons) if reasons else None,
        picker_id=payload.picker_id,
    )

    recent = report_repo.find_by_material_and_location(
        payload.material_type,
        report.location,
        trusted_only=True,
    )
    recent_prices = [item.price_per_kg for item in recent]
    verdict = anomaly_detector_service.deterministic_check(report, recent_prices)

    if not verdict.is_anomalous and anomaly_detector_service.ml_model is not None:
        material_prices = [
            item.price_per_kg
            for item in report_repo.find_by_material_and_location(
                payload.material_type,
                trusted_only=True,
            )
        ]
        if len(recent_prices) >= settings.MIN_REPORTS_FOR_BASELINE:
            import statistics

            median = statistics.median(material_prices or recent_prices)
            verdict = anomaly_detector_service.ml_check(report, median)

    if verdict.is_anomalous:
        report.needs_confirmation = True
        report.confirmation_reason = (
            f"{verdict.method} anomaly check: {verdict.reason}"
        )
        logger.warning(
            "REST report held for confirmation: material=%s location=%s reason=%s",
            report.material_type,
            report.location,
            report.confirmation_reason,
        )
    else:
        report_repo.add(report)

    return report
