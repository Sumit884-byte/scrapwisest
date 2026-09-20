from __future__ import annotations

from datetime import datetime, timezone
import pytest
from app.schemas.report import MaterialType, PriceReport, RawExtraction, ReportCreate
from app.schemas.price import PriceEstimate


def test_material_type_enum():
    assert MaterialType.PLASTIC_PET.value == "plastic_pet"
    assert MaterialType.METAL_ALUMINUM.value == "metal_aluminum"
    assert len(MaterialType) == 8


def test_price_report_serialization():
    report = PriceReport(
        material_type=MaterialType.PLASTIC_PET,
        quantity_kg=5.0,
        price_paid_pkr=700.0,
        price_paid_pkr_per_kg=140.0,
        location="Gulgasht",
        timestamp=datetime.now(timezone.utc),
    )
    json_str = report.model_dump_json()
    assert "plastic_pet" in json_str
    assert "Gulgasht" in json_str

    deserialized = PriceReport.model_validate_json(json_str)
    assert deserialized.price_paid_pkr_per_kg == 140.0


def test_raw_extraction_confidence_bounds():
    with pytest.raises(Exception):
        RawExtraction(
            material_type=MaterialType.CARDBOARD,
            material_confidence=1.5,  # Invalid: > 1.0
            quantity_confidence=0.5,
            price_confidence=0.5,
        )


def test_report_create_validation():
    valid = ReportCreate(
        material_type=MaterialType.GLASS,
        quantity_kg=15.0,
        price_paid_pkr=120.0,
        location="Cantt",
    )
    assert valid.quantity_kg == 15.0

    with pytest.raises(Exception):
        ReportCreate(
            material_type=MaterialType.GLASS,
            quantity_kg=-5.0,  # Invalid: <= 0
            price_paid_pkr=100.0,
            location="Cantt",
        )
