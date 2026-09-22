from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.voice_service import (
    audio_media_type,
    correct_transcript,
    prepare_speech_text,
    infer_lang_from_text,
    is_indian_lang,
    normalize_lang,
    sarvam_tts_language_code,
    should_keep_correction,
    transcribe_audio,
    voice_for_lang,
)


def test_normalize_lang_aliases_and_locales():
    assert normalize_lang("en-US") == "en"
    assert normalize_lang("Hindi") == "hi"
    assert normalize_lang("telugu") == "te"
    assert normalize_lang(None) == "en"


def test_voice_mapping_matches_detected_language():
    assert voice_for_lang("hi") == "hi-IN-SwaraNeural"
    assert voice_for_lang("te") == "te-IN-ShrutiNeural"
    assert voice_for_lang("ur") == "ur-IN-GulNeural"
    assert voice_for_lang("xx") == "en-US-AriaNeural"


def test_infer_lang_from_script():
    assert infer_lang_from_text("plastic ka rate kya hai") == "en"
    assert infer_lang_from_text("ప్లాస్టిక్ రేటు") == "te"
    assert infer_lang_from_text("پلاسٹک کا ریٹ") == "ur"
    assert infer_lang_from_text("प्लास्टिक का रेट") == "hi"


def test_transcribe_without_stt_keys_is_unavailable(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.endpoints.voice.stt_configured", lambda: False)
    res = client.post("/transcribe", files={"file": ("clip.webm", b"not-audio", "audio/webm")})
    assert res.status_code == 503


def test_indian_language_codes():
    assert is_indian_lang("hi-IN")
    assert is_indian_lang("te")
    assert is_indian_lang("ur")
    assert not is_indian_lang("en")
    assert not is_indian_lang("es")


def test_transcribe_keeps_sarvam_for_hindi(monkeypatch):
    monkeypatch.setattr("app.services.voice_service.sarvam_configured", lambda: True)
    monkeypatch.setattr("app.services.voice_service.groq_configured", lambda: True)
    monkeypatch.setattr(
        "app.services.voice_service._sarvam_transcribe",
        lambda *_args: ("प्लास्टिक का रेट क्या है", "hi"),
    )
    monkeypatch.setattr("app.services.voice_service.correct_transcript", lambda text, _lang: text)

    def _groq_should_not_run(*_args):
        raise AssertionError("Groq should not run for Hindi")

    monkeypatch.setattr("app.services.voice_service._groq_transcribe", _groq_should_not_run)
    text, lang = transcribe_audio(b"audio", "clip.webm")
    assert lang == "hi"
    assert "प्लास्टिक" in text


def test_transcribe_falls_back_to_groq_for_english(monkeypatch):
    monkeypatch.setattr("app.services.voice_service.sarvam_configured", lambda: True)
    monkeypatch.setattr("app.services.voice_service.groq_configured", lambda: True)
    monkeypatch.setattr(
        "app.services.voice_service._sarvam_transcribe",
        lambda *_args: ("What is the PET rate?", "en"),
    )
    monkeypatch.setattr(
        "app.services.voice_service._groq_transcribe",
        lambda *_args: ("What is the PET rate near me?", "en"),
    )
    monkeypatch.setattr("app.services.voice_service.correct_transcript", lambda text, _lang: text)
    text, lang = transcribe_audio(b"audio", "clip.webm")
    assert lang == "en"
    assert text == "What is the PET rate near me?"


def test_should_keep_nearby_word_fix():
    assert should_keep_correction("plaster ka rate kya hai", "plastic ka rate kya hai")
    assert should_keep_correction(
        "What is the rate of the plastic in full fat earth?",
        "What is the rate of plastic in Kolkata?",
    )
    assert should_keep_correction(
        "What is the rate of plastic in low and us?",
        "What is the rate of plastic in Lagos?",
    )
    assert not should_keep_correction(
        "plaster ka rate kya hai",
        "The user is asking about the market rate of plastic in their neighborhood.",
    )
    assert not should_keep_correction("plastic ka rate kya hai", "")


def test_correct_transcript_uses_neighbor_context(monkeypatch):
    class _Msg:
        content = "plastic ka rate kya hai"

    class _Choice:
        message = _Msg()

    class _Completion:
        choices = [_Choice()]

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    return _Completion()

    monkeypatch.setattr("app.services.voice_service.groq_configured", lambda: True)
    monkeypatch.setattr("app.services.voice_service._groq_client", lambda: _FakeClient())
    assert correct_transcript("plaster ka rate kya hai", "en") == "plastic ka rate kya hai"


def test_correct_transcript_can_restore_a_garbled_city(monkeypatch):
    class _Msg:
        content = "What is the rate of plastic in Kolkata?"

    class _Choice:
        message = _Msg()

    class _Completion:
        choices = [_Choice()]

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    return _Completion()

    monkeypatch.setattr("app.services.voice_service.groq_configured", lambda: True)
    monkeypatch.setattr("app.services.voice_service._groq_client", lambda: _FakeClient())
    raw = "What is the rate of the plastic in full fat earth?"
    assert correct_transcript(raw, "en") == "What is the rate of plastic in Kolkata?"


def test_correct_transcript_keeps_original_on_failure(monkeypatch):
    def _boom():
        raise RuntimeError("offline")

    monkeypatch.setattr("app.services.voice_service.groq_configured", lambda: True)
    monkeypatch.setattr("app.services.voice_service._groq_client", _boom)
    raw = "plaster ka rate kya hai"
    assert correct_transcript(raw, "en") == raw


def test_sarvam_tts_language_codes():
    assert sarvam_tts_language_code("hi") == "hi-IN"
    assert sarvam_tts_language_code("te") == "te-IN"
    assert sarvam_tts_language_code("ur") == "ur-IN"
    assert sarvam_tts_language_code("en") == "en-IN"
    assert sarvam_tts_language_code("es") is None


def test_sarvam_tts_attempts_cover_v3_and_v2():
    from app.services.voice_service import _sarvam_tts_attempts

    pairs = _sarvam_tts_attempts()
    models = {model for model, _speaker in pairs}
    assert "bulbul:v3" in models
    assert "bulbul:v2" in models
    assert pairs[0][0] in models


def test_prepare_speech_text_spells_pet():
    assert prepare_speech_text("PET plastic is 140 rupees") == "P E T plastic is 140 rupees"
    assert "P E T" in prepare_speech_text("भैया PET का रेट")
    assert "H D P E" in prepare_speech_text("HDPE pays less")
    assert prepare_speech_text("Cardboard rate") == "Cardboard rate"


def test_audio_media_type_detects_wav():
    assert audio_media_type(b"RIFF....WAVE") == "audio/wav"
    assert audio_media_type(b"ID3....") == "audio/mpeg"


def test_speak_rejects_empty_text(client: TestClient):
    res = client.post("/speak", data={"text": "   "})
    assert res.status_code == 400
