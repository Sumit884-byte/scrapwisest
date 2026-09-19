"""
Nemotron models on Nebius Token Factory.

The Best Apps and Agents track asks for a real app that stays responsive
and stretches credits: Ultra only when the call is a genuine judgment,
Nano/Super for everything a picker does all day.

  Nano   — structured extraction from messy field messages (cheap, fast)
  Super  — the chat copilot: language match, tool calls, follow-ups
  Ultra  — anomaly adjudication after cheaper tiers already flagged a report

Token Factory is OpenAI-compatible. Nano lives in eu-north1; Super and Ultra
live in us-central1. Override any of this with env vars.
"""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

# Official Token Factory model IDs (https://tokenfactory.nebius.com/model-catalog.md)
NANO_MODEL = os.getenv("NEMOTRON_NANO_MODEL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")
SUPER_MODEL = os.getenv("NEMOTRON_SUPER_MODEL", "nvidia/nemotron-3-super-120b-a12b")
ULTRA_MODEL = os.getenv("NEMOTRON_ULTRA_MODEL", "nvidia/Nemotron-3-Ultra-550b-a55b")

NANO_BASE_URL = os.getenv(
    "NEBIUS_NANO_BASE_URL",
    os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.eu-north1.nebius.com/v1/"),
)
REASONING_BASE_URL = os.getenv(
    "NEBIUS_REASONING_BASE_URL",
    os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.us-central1.nebius.com/v1/"),
)


def _api_key() -> str:
    key = os.getenv("NEBIUS_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "NEBIUS_API_KEY is missing. Create one at https://tokenfactory.nebius.com "
            "and put it in backend/.env (see .env.example)."
        )
    return key


def _chat_model(*, model: str, base_url: str, temperature: float = 0) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=_api_key(),
        temperature=temperature,
    )


def nano_model(temperature: float = 0) -> ChatOpenAI:
    """Fast everyday calls: report extraction, short structured output."""
    return _chat_model(model=NANO_MODEL, base_url=NANO_BASE_URL, temperature=temperature)


def super_model(temperature: float = 0) -> ChatOpenAI:
    """Everyday copilot: chat, tools, memory, follow-up questions."""
    return _chat_model(model=SUPER_MODEL, base_url=REASONING_BASE_URL, temperature=temperature)


def ultra_model(temperature: float = 0) -> ChatOpenAI:
    """Serious reasoning only: is this flagged sale legitimate or bad data?"""
    return _chat_model(model=ULTRA_MODEL, base_url=REASONING_BASE_URL, temperature=temperature)


def routing_info() -> dict:
    """Safe-to-expose model map for /health and the README."""
    return {
        "provider": "nebius-token-factory",
        "fast": {"model": NANO_MODEL, "role": "extract messy sale reports"},
        "everyday": {"model": SUPER_MODEL, "role": "picker chat + tools"},
        "reasoning": {"model": ULTRA_MODEL, "role": "anomaly judgment only"},
    }
