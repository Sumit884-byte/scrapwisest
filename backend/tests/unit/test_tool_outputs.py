from app.agent.tool_outputs import begin, end, record_price, record_report, reset
from app.agent.tools.price_estimator import estimate_price
from app.agent.workflows.pipeline import validate_and_build
from app.schemas.price import PriceEstimate
from app.schemas.report import MaterialType, RawExtraction


def test_begin_end_returns_values_written_on_slot():
    reset()
    begin("picker-a")
    record_price({"estimated_price_per_kg": 140})
    record_report({"quantity_kg": 2})
    price, report = end("picker-a")
    assert price["estimated_price_per_kg"] == 140
    assert report["quantity_kg"] == 2


def test_estimate_price_tool_records_structured_result():
    reset()
    begin("picker-price")
    payload = estimate_price("plastic_pet", "Income Colony")
    assert isinstance(payload, dict)
    assert payload["estimated_price_per_kg"] > 0
    price, _ = end("picker-price")
    assert isinstance(price, PriceEstimate)
    assert price.material_type == MaterialType.PLASTIC_PET


def test_validate_captures_report_when_confirmation_needed():
    reset()
    begin("picker-report")
    raw = RawExtraction(
        material_type=MaterialType.CARDBOARD,
        material_confidence=0.95,
        quantity_kg=None,
        quantity_confidence=0.2,
        price_paid_pkr=200.0,
        price_confidence=0.95,
        location_text="Samejabad",
    )
    validate_and_build({"raw_extraction": raw})
    _, report = end("picker-report")
    assert report is not None
    assert report.needs_confirmation is True
    assert report.location == "Samejabad"
