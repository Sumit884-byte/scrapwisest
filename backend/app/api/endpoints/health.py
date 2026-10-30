"""
Health check endpoints: liveness and readiness monitoring.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter
from app.agent.models import routing_info
from app.core.config import settings
from app.core.llm_budget import llm_budget
from app.services.bright_data_search import bright_data_configured
from app.services.parakeet_stt import parakeet_available, parakeet_status
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
        "search": {
            "configured": bright_data_configured() or bool(settings.TAVILY_API_KEY.strip()),
            "bright_data": bright_data_configured(),
            "tavily": bool(settings.TAVILY_API_KEY.strip()),
        },
        "llm_budget": llm_budget.snapshot(),
        "llm_max_tokens": {
            "nano": settings.LLM_NANO_MAX_TOKENS,
            "super": settings.LLM_SUPER_MAX_TOKENS,
            "ultra": settings.LLM_ULTRA_MAX_TOKENS,
        },
        "voice": {
            "stt": stt_configured(),
            "stt_providers": {
                "parakeet": parakeet_available(),
                "sarvam": sarvam_configured(),
                "groq": groq_configured(),
            },
            "parakeet": parakeet_status(),
            "tts": True,
            "tts_providers": {
                "sarvam": sarvam_configured(),
                "edge": True,
            },
        },
    }
