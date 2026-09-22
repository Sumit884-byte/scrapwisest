"""
Speech-to-text and text-to-speech.

Indian languages go through Sarvam Saaras / Bulbul. Other languages use
Groq Whisper and Edge-TTS.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import urllib.error
import urllib.request
import uuid
from typing import Optional

import edge_tts

from app.core.config import settings

logger = logging.getLogger(__name__)

VOICE_MAPPING = {
    "en": "en-US-AriaNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "hi": "hi-IN-SwaraNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ja": "ja-JP-NanamiNeural",
    "ar": "ar-SA-ZariyahNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "te": "te-IN-ShrutiNeural",
    "ur": "ur-IN-GulNeural",
    "ta": "ta-IN-PallaviNeural",
    "bn": "bn-IN-TanishaaNeural",
    "it": "it-IT-ElsaNeural",
    "ko": "ko-KR-SunHiNeural",
    "id": "id-ID-GadisNeural",
    "tr": "tr-TR-EmelNeural",
    "nl": "nl-NL-FennaNeural",
    "pl": "pl-PL-ZofiaNeural",
    "vi": "vi-VN-HoaiMyNeural",
    "th": "th-TH-PremwadeeNeural",
}
DEFAULT_VOICE = "en-US-AriaNeural"

_LANG_ALIASES = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "hindi": "hi",
    "chinese": "zh",
    "mandarin": "zh",
    "japanese": "ja",
    "arabic": "ar",
    "portuguese": "pt",
    "russian": "ru",
    "telugu": "te",
    "urdu": "ur",
    "tamil": "ta",
    "bengali": "bn",
}

_SCRIPT_LANG = (
    (re.compile(r"[\u0C00-\u0C7F]"), "te"),
    (re.compile(r"[\u0900-\u097F]"), "hi"),
    (re.compile(r"[\u0600-\u06FF]"), "ur"),
    (re.compile(r"[\u4E00-\u9FFF]"), "zh"),
    (re.compile(r"[\u3040-\u30FF]"), "ja"),
    (re.compile(r"[\u0B80-\u0BFF]"), "ta"),
    (re.compile(r"[\u0980-\u09FF]"), "bn"),
)


_INDIAN_LANGS = {
    "as",
    "bn",
    "br",
    "doi",
    "gu",
    "hi",
    "kn",
    "ks",
    "kok",
    "mai",
    "ml",
    "mni",
    "mr",
    "ne",
    "od",
    "or",
    "pa",
    "sa",
    "sat",
    "sd",
    "ta",
    "te",
    "ur",
}


def groq_configured() -> bool:
    return bool(settings.GROQ_API_KEY.strip())


def sarvam_configured() -> bool:
    return bool(settings.SARVAM_API_KEY.strip())


def stt_configured() -> bool:
    return groq_configured() or sarvam_configured()


def is_indian_lang(lang: Optional[str]) -> bool:
    return normalize_lang(lang) in _INDIAN_LANGS


def normalize_lang(raw: Optional[str]) -> str:
    if not raw:
        return "en"
    code = raw.strip().lower().replace("_", "-")
    if "-" in code:
        code = code.split("-", 1)[0]
    code = _LANG_ALIASES.get(code, code)
    return code if len(code) == 2 else "en"


def infer_lang_from_text(text: str) -> str:
    for pattern, lang in _SCRIPT_LANG:
        if pattern.search(text):
            return lang
    return "en"


def voice_for_lang(lang: Optional[str]) -> str:
    return VOICE_MAPPING.get(normalize_lang(lang), DEFAULT_VOICE)


_SARVAM_TTS_LANG = {
    "as": "as-IN",
    "bn": "bn-IN",
    "en": "en-IN",
    "gu": "gu-IN",
    "hi": "hi-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "mr": "mr-IN",
    "ne": "ne-IN",
    "od": "od-IN",
    "or": "od-IN",
    "pa": "pa-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "ur": "ur-IN",
}


def sarvam_tts_language_code(lang: Optional[str]) -> Optional[str]:
    return _SARVAM_TTS_LANG.get(normalize_lang(lang))


def audio_media_type(audio: bytes) -> str:
    if audio.startswith(b"RIFF"):
        return "audio/wav"
    return "audio/mpeg"


_SPEAK_ACRONYMS = (
    (re.compile(r"\bHDPE\b", re.IGNORECASE), "H D P E"),
    (re.compile(r"\bPET\b", re.IGNORECASE), "P E T"),
    (re.compile(r"\bPVC\b", re.IGNORECASE), "P V C"),
)


def prepare_speech_text(text: str) -> str:
    """Spell scrap acronyms so TTS does not say 'pet' for PET plastic."""
    spoken = text
    for pattern, replacement in _SPEAK_ACRONYMS:
        spoken = pattern.sub(replacement, spoken)
    return spoken


# Style hint only — no city, country, currency, or language list.
# Whisper uses this to treat trailing place phrases as proper nouns.
_WHISPER_PROMPT = (
    "Scrap material prices by weight. After in, at, or near comes a real "
    "city or neighborhood anywhere in the world. Spell place names correctly."
)

_STT_FIX_SYSTEM = """\
You repair speech-to-text mistakes using nearby words as context.

The speaker is asking about scrap materials (plastic, steel, aluminum, glass, cardboard, paper), weight (kilo/kg), prices, and places.

Rules:
- Work for any spoken language and any country. Do not prefer a region, city list, or currency.
- Keep the same language and script the speaker used.
- Only fix words that are clearly misheard given the surrounding words (e.g. "plaster ka rate" → "plastic ka rate").
- After in / at / near / from, the next words are usually a place. If they are garbled nonsense (not a real city, town, or neighborhood anywhere in the world), replace that fragment with the real place the sound and sentence imply. Do not default to a favorite city or country.
- You may fix obvious number/word slips ("to kilo" → "2 kilo") when neighbors make the intent clear.
- Do not translate, summarize, complete the thought, or add facts that were not spoken.
- If the transcript already makes sense, return it unchanged.
- Reply with ONLY the corrected transcript. No quotes, labels, or explanation.
"""


def _groq_client():
    from groq import Groq

    return Groq(api_key=settings.GROQ_API_KEY.strip())


def _strip_fix_wrapper(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    return cleaned.strip().strip('"').strip("'").strip()


def should_keep_correction(original: str, fixed: str) -> bool:
    """Reject model output that rewrote or padded the transcript instead of repairing it."""
    fixed = _strip_fix_wrapper(fixed)
    if not fixed:
        return False
    orig_len = max(len(original.strip()), 1)
    if len(fixed) > max(48, int(orig_len * 1.8)):
        return False
    if len(fixed) < max(1, int(orig_len * 0.4)):
        return False
    return True


def correct_transcript(text: str, language: str) -> str:
    """Second layer: fix small ASR slips so the phrase makes sense with its neighbors."""
    original = text.strip()
    if not original or not groq_configured():
        return original

    try:
        completion = _groq_client().chat.completions.create(
            model=settings.GROQ_STT_FIX_MODEL,
            temperature=0,
            max_tokens=200,
            messages=[
                {"role": "system", "content": _STT_FIX_SYSTEM},
                {
                    "role": "user",
                    "content": f"Detected language: {language}\nTranscript: {original}",
                },
            ],
        )
        candidate = (completion.choices[0].message.content or "").strip()
    except Exception:
        logger.exception("STT correction layer failed; keeping Whisper text")
        return original

    if not should_keep_correction(original, candidate):
        logger.info("STT correction rejected as a rewrite: %r -> %r", original[:80], candidate[:80])
        return original

    fixed = _strip_fix_wrapper(candidate)
    if fixed != original:
        logger.info("STT correction applied: %r -> %r", original[:80], fixed[:80])
    return fixed


def _sarvam_transcribe(audio_bytes: bytes, filename: str) -> tuple[str, str]:
    """Indian-language STT via Sarvam Saaras. Language is auto-detected."""
    boundary = uuid.uuid4().hex
    safe_name = filename or "audio.webm"
    preamble = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="model"\r\n\r\n'
        f"{settings.SARVAM_STT_MODEL}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="language_code"\r\n\r\n'
        "unknown\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="mode"\r\n\r\n'
        f"{settings.SARVAM_STT_MODE}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    body = preamble + audio_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = urllib.request.Request(
        "https://api.sarvam.ai/speech-to-text",
        data=body,
        method="POST",
        headers={
            "api-subscription-key": settings.SARVAM_API_KEY.strip(),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Sarvam STT failed ({exc.code}): {detail}") from exc

    text = (payload.get("transcript") or "").strip()
    detected = normalize_lang(payload.get("language_code"))
    if detected == "en":
        detected = infer_lang_from_text(text)
    logger.info("Sarvam detected language=%s text=%r", detected, text[:80])
    return text, detected


def _groq_transcribe(audio_bytes: bytes, filename: str) -> tuple[str, str]:
    client = _groq_client()
    safe_name = filename or "audio.webm"
    transcription = client.audio.transcriptions.create(
        file=(safe_name, audio_bytes),
        model=settings.GROQ_WHISPER_MODEL,
        prompt=_WHISPER_PROMPT,
        temperature=0,
        response_format="verbose_json",
    )
    text = (getattr(transcription, "text", None) or "").strip()
    detected = normalize_lang(getattr(transcription, "language", None))
    logger.info("Whisper detected language=%s text=%r", detected, text[:80])
    return text, detected


def transcribe_audio(audio_bytes: bytes, filename: str) -> tuple[str, str]:
    """Return (text, iso-639-1 language). Indic → Sarvam; otherwise Groq Whisper."""
    if not stt_configured():
        raise RuntimeError(
            "No STT key is set. Add SARVAM_API_KEY for Indian languages "
            "or GROQ_API_KEY for other languages."
        )

    text = ""
    detected = "en"
    used_sarvam = False

    if sarvam_configured():
        try:
            text, detected = _sarvam_transcribe(audio_bytes, filename)
            used_sarvam = True
        except Exception:
            logger.exception("Sarvam STT failed")
            if not groq_configured():
                raise

    if used_sarvam and is_indian_lang(detected):
        if text:
            text = correct_transcript(text, detected)
        return text, detected

    if groq_configured():
        text, detected = _groq_transcribe(audio_bytes, filename)
        if text:
            text = correct_transcript(text, detected)
        return text, detected

    if text:
        text = correct_transcript(text, detected)
    return text, detected


_SARVAM_TTS_MODELS = ("bulbul:v3", "bulbul:v2")
_SARVAM_TTS_SPEAKERS = {
    "bulbul:v3": ("priya", "shubh", "simran", "anushka"),
    "bulbul:v2": ("anushka", "abhilash", "manisha", "vidya"),
}
_working_sarvam_tts: tuple[str, str] | None = None


def _sarvam_tts_attempts() -> list[tuple[str, str]]:
    preferred_model = (settings.SARVAM_TTS_MODEL or "").strip() or "bulbul:v3"
    preferred_speaker = (settings.SARVAM_TTS_SPEAKER or "").strip()
    seen: set[tuple[str, str]] = set()
    attempts: list[tuple[str, str]] = []
    models = [preferred_model] + [m for m in _SARVAM_TTS_MODELS if m != preferred_model]
    for model in models:
        speakers = list(_SARVAM_TTS_SPEAKERS.get(model, ("priya",)))
        if preferred_speaker:
            speakers = [preferred_speaker] + [s for s in speakers if s != preferred_speaker]
        for speaker in speakers:
            pair = (model, speaker)
            if pair not in seen:
                seen.add(pair)
                attempts.append(pair)
    return attempts


def _sarvam_tts_request(text: str, target: str, model: str, speaker: str) -> bytes:
    payload = json.dumps(
        {
            "text": text,
            "target_language_code": target,
            "model": model,
            "speaker": speaker,
            "enable_preprocessing": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.sarvam.ai/text-to-speech",
        data=payload,
        method="POST",
        headers={
            "api-subscription-key": settings.SARVAM_API_KEY.strip(),
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    audios = body.get("audios") or []
    if not audios:
        raise RuntimeError("Sarvam TTS returned no audio.")
    return base64.b64decode("".join(audios))


def _sarvam_speak(text: str, lang: str) -> bytes:
    global _working_sarvam_tts
    target = sarvam_tts_language_code(lang)
    if not target:
        raise RuntimeError(f"Sarvam TTS has no voice for {lang}")

    attempts = _sarvam_tts_attempts()
    if _working_sarvam_tts and _working_sarvam_tts in attempts:
        attempts = [_working_sarvam_tts] + [pair for pair in attempts if pair != _working_sarvam_tts]

    last_error: Exception | None = None
    for model, speaker in attempts:
        pieces: list[bytes] = []
        try:
            limit = 1500 if model.endswith("v2") else 2400
            for start in range(0, len(text), limit):
                pieces.append(_sarvam_tts_request(text[start : start + limit], target, model, speaker))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            last_error = RuntimeError(f"Sarvam TTS {model}/{speaker} failed ({exc.code}): {detail}")
            logger.info("Sarvam TTS %s/%s unavailable: %s", model, speaker, exc.code)
            if exc.code == 402:
                break
            continue
        except Exception as exc:
            last_error = exc
            logger.info("Sarvam TTS %s/%s failed: %s", model, speaker, exc)
            continue
        _working_sarvam_tts = (model, speaker)
        logger.info("Sarvam TTS model=%s speaker=%s lang=%s", model, speaker, target)
        return b"".join(pieces)

    if last_error:
        raise last_error
    raise RuntimeError("Sarvam TTS has no available model.")


async def _edge_speak(text: str, lang: str) -> bytes:
    voice = voice_for_lang(lang)
    logger.info("Edge-TTS voice=%s lang=%s", voice, lang)
    communicate = edge_tts.Communicate(text, voice)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    if not chunks:
        raise RuntimeError("Edge-TTS returned no audio.")
    return b"".join(chunks)


async def synthesize_speech(text: str, lang: Optional[str] = None) -> bytes:
    """Speak with Sarvam Bulbul for Indian languages; Edge-TTS otherwise."""
    resolved = normalize_lang(lang) if lang else infer_lang_from_text(text)
    spoken = prepare_speech_text(text)
    if sarvam_configured() and sarvam_tts_language_code(resolved):
        try:
            return await asyncio.to_thread(_sarvam_speak, spoken, resolved)
        except Exception:
            logger.exception("Sarvam TTS failed; falling back to Edge-TTS")
    return await _edge_speak(spoken, resolved)
