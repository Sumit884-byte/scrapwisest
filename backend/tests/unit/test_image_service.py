from app.services.image_service import map_classifier_label


def test_cnn_mapping_only_maps_specific_supported_materials():
    assert map_classifier_label("cardboard") == "cardboard"
    assert map_classifier_label("paper") == "mixed_paper"
    assert map_classifier_label("glass") == "glass"


def test_cnn_mapping_does_not_guess_plastic_or_metal_subtypes():
    assert map_classifier_label("plastic") is None
    assert map_classifier_label("metal") is None
