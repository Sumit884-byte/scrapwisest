"""
Health check endpoints: liveness and readiness monitoring.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter
from app.agent.models import routing_info
from app.core.config import settings
from app.services.voice_service import groq_configured, sarvam_configured, stt_configured

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """
    Health check endpoint returning system status and LLM model routing details.
    """
    logger.info("Health check endpoint accessed")
    return {
        "status": "ok",
        "models": routing_info(),
        "version": settings.VERSION,
        "environment": "development" if settings.DEBUG else "production",
        "vision": bool(settings.GROQ_API_KEY.strip()),
        "voice": {
            "stt": stt_configured(),
            "stt_providers": {
                "sarvam": sarvam_configured(),
                "groq": groq_configured(),
            },
            "tts": True,
            "tts_providers": {
                "sarvam": sarvam_configured(),
                "edge": True,
            },
        },
    }
