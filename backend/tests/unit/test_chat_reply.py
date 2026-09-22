from app.api.endpoints.chat import (
    clean_reply,
    hindi_words,
    parse_material_reply,
    picker_context_tags,
    _material_rate_reply,
)
from app.schemas.report import MaterialType


def test_clean_reply_drops_duplicate_and_tier_leak():
    raw = (
        "PET plastic rate 141.5 rupay per kg (city-level estimate).\n\n"
        "PET plastic rate 141.5 rupay per kg (city-level estimate)."
    )
    assert clean_reply(raw) == "PET plastic rate 141.5 rupay per kg."


def test_parse_material_reply_reads_short_answers():
    assert parse_material_reply("pet") is MaterialType.PLASTIC_PET
    assert parse_material_reply("HDPE") is MaterialType.PLASTIC_HDPE
    assert parse_material_reply("it's pet") is MaterialType.PLASTIC_PET
    assert parse_material_reply("plastic dhar entha per kg?") is None


def test_picker_context_tags_include_place_and_language():
    assert picker_context_tags("hi-latn", "Kolkata", "India") == (
        "[picker_place: Kolkata, India]\n[reply_language: Hinglish (Roman letters)]"
    )
    assert "Hindi (Devanagari" in picker_context_tags("hi", "", "")
    assert picker_context_tags("auto", "", "") == ""


def test_hindi_rate_uses_hindi_place_and_material():
    assert hindi_words("Kolkata, India") == "कोलकाता, भारत"
    assert "कोलकाता" in _material_rate_reply("PET", "141.5", "Kolkata India", "hi")
    assert "पीईटी" in _material_rate_reply("PET", "141.5", "Kolkata India", "hi")
    assert "Kolkata" not in _material_rate_reply("PET", "141.5", "Kolkata India", "hi")
