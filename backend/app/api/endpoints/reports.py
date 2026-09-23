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
from app.schemas.market import canonicalize_country, is_unknown_currency, resolve_currency
from app.services.location_resolver import (
    normalize_location,
    normalize_place_part,
    validate_market_fields,
)
from app.services.price_estimator import price_band_for
from app.services.anomaly_detector import anomaly_detector_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=List[ReportResponse])
async def list_reports(
    material: Optional[str] = Query(None, description="Filter by material type"),
    location: Optional[str] = Query(None, description="Filter by neighborhood/location"),
    currency: Optional[str] = Query(None, description="Filter by ISO currency"),
    country: Optional[str] = Query(None, description="Filter by country"),
    city: Optional[str] = Query(None, description="Filter by city"),
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

    if currency:
        wanted = resolve_currency(currency, None, country)
        reports = [r for r in reports if r.currency == wanted]
    if country:
        wanted_country = canonicalize_country(country)
        reports = [r for r in reports if r.country == wanted_country]
    if city:
        wanted_city = city.strip().lower()
        reports = [r for r in reports if (r.city or "").strip().lower() == wanted_city]

    return reports


@router.post("", response_model=ReportResponse, status_code=201)
async def create_report(payload: ReportCreate):
    """
    Directly log a validated scrap sale report into the system.
    """
    price_per_kg = payload.total_price / payload.quantity_kg
    country = canonicalize_country(payload.country)
    city = normalize_place_part(payload.city)
    neighborhood = normalize_place_part(payload.neighborhood)
    currency = resolve_currency(payload.currency, None, country)

    reasons: list[str] = validate_market_fields(currency, country, city, neighborhood)
    if is_unknown_currency(currency):
        reasons.append("currency unknown")

    band = price_band_for(payload.material_type, currency)
    if band is not None:
        min_band, max_band = band
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

    wanted = report.market_key()
    recent = [
        item
        for item in report_repo.find_by_material_and_location(
            payload.material_type,
            report.location,
            trusted_only=True,
        )
        if item.market_key() == wanted
    ]
    recent_prices = [item.price_per_kg for item in recent]
    verdict = anomaly_detector_service.deterministic_check(report, recent_prices)

    if not verdict.is_anomalous and anomaly_detector_service.ml_model is not None:
        material_prices = [
            item.price_per_kg
            for item in report_repo.find_by_material_and_location(
                payload.material_type,
                trusted_only=True,
            )
            if item.market_key() == wanted
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
