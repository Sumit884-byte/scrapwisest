from app.agent.workflows.pipeline import _material_label, validate_and_build
from app.schemas.report import MaterialType, RawExtraction


def test_material_label_accepts_str_enum_values():
    assert _material_label("plastic_pet") == "plastic_pet"
    assert _material_label(MaterialType.PLASTIC_PET) == "plastic_pet"


def test_validate_and_build_when_material_is_plain_string():
    raw = RawExtraction(
        material_type=MaterialType.PLASTIC_PET,
        material_confidence=0.95,
        quantity_kg=2.0,
        quantity_confidence=0.95,
        price_paid_pkr=300.0,
        price_confidence=0.95,
        location_text="Income Colony",
    )
    raw.material_type = "plastic_pet"
    result = validate_and_build({"raw_extraction": raw})
    assert result["price_report"].material_type in (MaterialType.PLASTIC_PET, "plastic_pet")
    assert result["price_report"].quantity_kg == 2.0
