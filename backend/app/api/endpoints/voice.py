"""
Voice endpoints: Groq Whisper transcription and Edge-TTS speech.
Chat replies still go through the existing /chat agent (Nemotron).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.config import settings
from app.core.exceptions import QuotaExceededError
from app.core.llm_budget import clip_text, reserve_llm
from app.services.voice_service import (
    audio_media_type,
    stt_configured,
    synthesize_speech,
    transcribe_audio,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])

_MAX_AUDIO_BYTES = 12 * 1024 * 1024


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    if not stt_configured():
        raise HTTPException(
            status_code=503,
            detail="Voice transcription is not configured (local Parakeet, SARVAM_API_KEY, or GROQ_API_KEY).",
        )
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio upload.")
    if len(audio) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio is too large (max 12MB).")

    filename = file.filename or "audio.webm"
    try:
        reserve_llm("transcribe")
        text, language = await asyncio.to_thread(transcribe_audio, audio, filename)
    except QuotaExceededError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        logger.exception("Speech transcription failed")
        raise HTTPException(status_code=500, detail="Could not transcribe that audio.") from None

    if not text:
        raise HTTPException(status_code=422, detail="Could not hear anything — please try again.")
    return {"text": text, "language": language}


@router.post("/speak")
async def speak(
    text: str = Form(...),
    language: str = Form(""),
    voice: str = Form(""),
):
    cleaned = clip_text(text, settings.LLM_MAX_SPEAK_CHARS)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Provide text to speak.")
    try:
        audio = await synthesize_speech(cleaned, language or None, voice or None)
    except Exception:
        logger.exception("Speech synthesis failed")
        raise HTTPException(status_code=500, detail="Could not generate speech.") from None
    return Response(content=audio, media_type=audio_media_type(audio))
