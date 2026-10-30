from app.services.image_service import (
    average_volume_from_vision,
    detected_material_tag,
    format_classification_reply,
    map_classifier_label,
    normalize_vision_label,
    parse_vision_classification,
)


def test_cnn_mapping_only_maps_specific_supported_materials():
    assert map_classifier_label("cardboard") == "cardboard"
    assert map_classifier_label("paper") == "mixed_paper"
    assert map_classifier_label("glass") == "glass"


def test_cnn_mapping_does_not_guess_plastic_or_metal_subtypes():
    assert map_classifier_label("plastic") is None
    assert map_classifier_label("metal") is None


def test_vision_payload_asks_for_plastic_subtype():
    result = parse_vision_classification('{"label": "plastic", "confidence": 0.91}')
    assert result == {
        "error": "ambiguous_material",
        "category": "plastic",
        "confidence": 0.91,
        "source": "vision",
    }


def test_vision_payload_maps_pet_bottles_to_plastic_pet():
    result = parse_vision_classification('{"label": "plastic bottles", "confidence": 0.88}')
    assert result == {
        "material_type": "plastic_pet",
        "confidence": 0.88,
        "source": "vision",
    }


def test_vision_payload_maps_soda_cans_to_aluminum():
    result = parse_vision_classification('{"label": "aluminum cans", "confidence": 0.84}')
    assert result["material_type"] == "metal_aluminum"


def test_normalize_vision_label_aliases():
    assert normalize_vision_label("PET") == "plastic_pet"
    assert normalize_vision_label("milk jug") == "plastic_hdpe"
    assert normalize_vision_label("newspaper") == "paper"


def test_vision_payload_treats_unrelated_labels_as_not_scrap():
    result = parse_vision_classification('{"label": "selfie", "confidence": 0.9}')
    assert result["error"] == "not_scrap"


def test_not_scrap_reply_asks_for_real_scrap_photo():
    reply = format_classification_reply({"error": "not_scrap", "source": "vision"})
    assert reply.startswith("🙂")
    assert "scrap" in reply.lower()
    assert "portrait" in reply.lower() or "unrelated" in reply.lower()


def test_vision_payload_averages_volume_range_and_density_kg():
    result = parse_vision_classification(
        '{"label": "plastic_pet", "confidence": 0.9, '
        '"volume_liters": 80, "volume_liters_low": 60, '
        '"volume_liters_high": 100, "estimated_kg": 4}'
    )
    assert result["material_type"] == "plastic_pet"
    assert result["estimated_volume_liters"] == 80.0
    # density kg = 80 L * 35 kg/m³ / 1000 = 2.8; average with 4 kg = 3.4
    assert result["estimated_quantity_kg"] == 3.4
    assert result["volume_source"] == "vision"


def test_average_volume_uses_density_when_model_omits_kg():
    volume = average_volume_from_vision({"volume_liters": 100}, "metal_aluminum")
    assert volume["estimated_volume_liters"] == 100.0
    assert volume["estimated_quantity_kg"] == 6.5


def test_classification_reply_mentions_visible_volume():
    reply = format_classification_reply(
        {
            "material_type": "plastic_pet",
            "confidence": 0.9,
            "source": "vision",
            "estimated_quantity_kg": 3.4,
            "estimated_volume_liters": 80,
        }
    )
    assert "3.4 kg" in reply
    assert "80 L" in reply
    assert "sale" not in reply.lower()


def test_detected_material_tag_includes_volume():
    tag = detected_material_tag(
        {
            "material_type": "plastic_pet",
            "confidence": 0.88,
            "estimated_quantity_kg": 3.4,
            "estimated_volume_liters": 80,
        }
    )
    assert tag == (
        "[detected_material: plastic_pet, confidence: 0.88, "
        "volume_kg: 3.40, volume_l: 80.0]"
    )
