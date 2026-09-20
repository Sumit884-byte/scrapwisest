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
        reports = [r for r in all_reps if r.location.strip().lower() == location.strip().lower()]
    else:
        reports = report_repo.trusted_reports() if trusted_only else report_repo.all_reports()

    return reports


@router.post("", response_model=ReportResponse, status_code=201)
async def create_report(payload: ReportCreate):
    """
    Directly log a validated scrap sale report into the system.
    """
    price_per_kg = payload.price_paid_pkr / payload.quantity_kg
    min_band, max_band = settings.PRICE_PER_KG_BANDS.get(
        payload.material_type.value, (5.0, 500.0)
    )
    needs_confirm = not (min_band <= price_per_kg <= max_band)
    confirm_reason = (
        f"Price per kg ({price_per_kg:.1f}) outside sanity range [{min_band}, {max_band}]"
        if needs_confirm
        else None
    )

    report = PriceReport(
        material_type=payload.material_type,
        quantity_kg=payload.quantity_kg,
        price_paid_pkr=payload.price_paid_pkr,
        price_paid_pkr_per_kg=round(price_per_kg, 2),
        location=payload.location.strip(),
        timestamp=datetime.now(timezone.utc),
        needs_confirmation=needs_confirm,
        confirmation_reason=confirm_reason,
        picker_id=payload.picker_id,
    )

    report_repo.add(report)
    return report
