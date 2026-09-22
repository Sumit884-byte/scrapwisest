"""
Qwen models configured on xKiro free API gateway.
"""

from __future__ import annotations

import logging
from langchain_openai import ChatOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)


def _api_key() -> str:
    key = settings.XKIRO_API_KEY.strip()
    if not key or key == "your-api-key-here":
        raise RuntimeError(
            "XKIRO_API_KEY is missing or still a placeholder. Get your free API key at "
            "https://xkiro.com/dashboard/api-keys and set it in backend/.env."
        )
    return key


def _chat_model(*, model: str, base_url: str | None = None, temperature: float = 0) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        base_url=base_url or settings.XKIRO_BASE_URL,
        api_key=_api_key(),
        temperature=temperature,
        timeout=settings.XKIRO_REQUEST_TIMEOUT,
        max_retries=settings.XKIRO_MAX_RETRIES,
    )


def nano_model(temperature: float = 0) -> ChatOpenAI:
    """Fast everyday calls: report extraction, short structured output using Qwen."""
    return _chat_model(
        model=settings.XKIRO_FAST_MODEL,
        base_url=settings.XKIRO_BASE_URL,
        temperature=temperature,
    )


def super_model(temperature: float = 0) -> ChatOpenAI:
    """Everyday copilot: chat, tools, memory, follow-up questions using Qwen."""
    return _chat_model(
        model=settings.XKIRO_EVERYDAY_MODEL,
        base_url=settings.XKIRO_BASE_URL,
        temperature=temperature,
    )


def ultra_model(temperature: float = 0) -> ChatOpenAI:
    """Reasoning model: anomaly judgment using Qwen."""
    return _chat_model(
        model=settings.XKIRO_REASONING_MODEL,
        base_url=settings.XKIRO_BASE_URL,
        temperature=temperature,
    )


def routing_info() -> dict:
    """Safe-to-expose model map for /health and documentation."""
    return {
        "provider": "xkiro",
        "fast": {"model": settings.XKIRO_FAST_MODEL, "role": "extract messy sale reports"},
        "everyday": {"model": settings.XKIRO_EVERYDAY_MODEL, "role": "picker chat + tools"},
        "reasoning": {"model": settings.XKIRO_REASONING_MODEL, "role": "anomaly judgment only"},
    }
