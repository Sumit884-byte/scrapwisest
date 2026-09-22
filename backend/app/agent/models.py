"""
Dynamic LLM model router.
Dispatches to either xKiro (Qwen) or Nebius (Nemotron) based on settings.LLM_PROVIDER.
"""

from __future__ import annotations

import logging
from langchain_openai import ChatOpenAI
from app.core.config import settings
from app.agent import nemotron, qwen

logger = logging.getLogger(__name__)


def get_active_provider_module():
    """Returns the module corresponding to the active LLM provider."""
    if settings.resolved_llm_provider() == "nebius":
        return nemotron
    return qwen


def nano_model(temperature: float = 0) -> ChatOpenAI:
    """Fast model dispatcher (extraction / structured output)."""
    return get_active_provider_module().nano_model(temperature=temperature)


def super_model(temperature: float = 0) -> ChatOpenAI:
    """Everyday copilot model dispatcher (agent, chat, tools)."""
    return get_active_provider_module().super_model(temperature=temperature)


def ultra_model(temperature: float = 0) -> ChatOpenAI:
    """Reasoning model dispatcher (anomaly judgment)."""
    return get_active_provider_module().ultra_model(temperature=temperature)


def routing_info() -> dict:
    """Returns routing info for the currently active provider."""
    return get_active_provider_module().routing_info()
