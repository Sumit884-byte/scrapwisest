from app.services.image_service import map_classifier_label, parse_vision_classification


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


def test_vision_payload_rejects_unknown_labels():
    assert parse_vision_classification('{"label": "rc_car", "confidence": 0.9}') is None
