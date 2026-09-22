"""
Nemotron models configured on Nebius Token Factory.
"""

from __future__ import annotations

import logging
from langchain_openai import ChatOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)


def _api_key() -> str:
    key = settings.NEBIUS_API_KEY.strip()
    if not key:
        raise RuntimeError(
            "NEBIUS_API_KEY is missing. Create one at https://tokenfactory.nebius.com "
            "and set it in your .env file."
        )
    return key


def _chat_model(*, model: str, base_url: str, temperature: float = 0) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=_api_key(),
        temperature=temperature,
        max_retries=5,
    )


def nano_model(temperature: float = 0) -> ChatOpenAI:
    """Fast everyday calls: report extraction, short structured output."""
    return _chat_model(
        model=settings.NEMOTRON_NANO_MODEL,
        base_url=settings.NEBIUS_NANO_BASE_URL,
        temperature=temperature,
    )


def super_model(temperature: float = 0) -> ChatOpenAI:
    """Everyday copilot: chat, tools, memory, follow-up questions."""
    return _chat_model(
        model=settings.NEMOTRON_SUPER_MODEL,
        base_url=settings.NEBIUS_REASONING_BASE_URL,
        temperature=temperature,
    )


def ultra_model(temperature: float = 0) -> ChatOpenAI:
    """Serious reasoning only: is this flagged sale legitimate or bad data?"""
    return _chat_model(
        model=settings.NEMOTRON_ULTRA_MODEL,
        base_url=settings.NEBIUS_REASONING_BASE_URL,
        temperature=temperature,
    )


def routing_info() -> dict:
    """Safe-to-expose model map for /health and documentation."""
    return {
        "provider": "nebius-token-factory",
        "fast": {"model": settings.NEMOTRON_NANO_MODEL, "role": "extract messy sale reports"},
        "everyday": {"model": settings.NEMOTRON_SUPER_MODEL, "role": "picker chat + tools"},
        "reasoning": {"model": settings.NEMOTRON_ULTRA_MODEL, "role": "anomaly judgment only"},
    }
