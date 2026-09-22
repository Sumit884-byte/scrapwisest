"""
Nemotron models configured on Nebius Token Factory.

Nano is hosted in eu-north1; Super and Ultra in us-central1. When a picker
shares location we pick the nearer region and the everyday model that lives
there, so the first hop is shorter.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from langchain_openai import ChatOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

REGIONS: dict[str, dict[str, Any]] = {
    "eu-north1": {
        "id": "eu-north1",
        "label": "Europe",
        "lat": 60.1699,
        "lng": 24.9384,
        "base_url": "https://api.tokenfactory.eu-north1.nebius.com/v1/",
        "everyday_role": "fast",
    },
    "us-central1": {
        "id": "us-central1",
        "label": "US Central",
        "lat": 41.2619,
        "lng": -95.8608,
        "base_url": "https://api.tokenfactory.us-central1.nebius.com/v1/",
        "everyday_role": "everyday",
    },
}


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
        timeout=settings.NEBIUS_REQUEST_TIMEOUT,
        max_retries=settings.NEBIUS_MAX_RETRIES,
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
    return ChatOpenAI(
        model=settings.NEMOTRON_ULTRA_MODEL,
        base_url=settings.NEBIUS_REASONING_BASE_URL,
        api_key=_api_key(),
        temperature=temperature,
        timeout=max(settings.NEBIUS_REQUEST_TIMEOUT, 90.0),
        max_retries=settings.NEBIUS_MAX_RETRIES,
    )


def normalize_region(region_id: str | None) -> str | None:
    if not region_id:
        return None
    key = region_id.strip().lower()
    return key if key in REGIONS else None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def nearest_region(lat: float, lng: float) -> str:
    return min(
        REGIONS.values(),
        key=lambda spec: _haversine_km(lat, lng, float(spec["lat"]), float(spec["lng"])),
    )["id"]


def resolve_region(region_id: str | None) -> str:
    if settings.PIN_TOKEN_FACTORY_REGION:
        return settings.TOKEN_FACTORY_DEFAULT_REGION
    return normalize_region(region_id) or settings.TOKEN_FACTORY_DEFAULT_REGION


def _everyday_spec(region_id: str) -> tuple[str, str]:
    if region_id == "eu-north1":
        return settings.NEMOTRON_NANO_MODEL, settings.NEBIUS_NANO_BASE_URL
    return settings.NEMOTRON_SUPER_MODEL, settings.NEBIUS_REASONING_BASE_URL


def everyday_model(region_id: str | None = None, temperature: float = 0) -> ChatOpenAI:
    resolved = resolve_region(region_id)
    model, base_url = _everyday_spec(resolved)
    return _chat_model(model=model, base_url=base_url, temperature=temperature)


def region_info(region_id: str | None) -> dict[str, Any]:
    spec = REGIONS[resolve_region(region_id)]
    model, _ = _everyday_spec(spec["id"])
    return {"id": spec["id"], "label": spec["label"], "everyday_model": model}


def public_regions() -> list[dict[str, Any]]:
    return [
        {
            "id": spec["id"],
            "label": spec["label"],
            "lat": spec["lat"],
            "lng": spec["lng"],
            "everyday": spec["everyday_role"],
        }
        for spec in REGIONS.values()
    ]


def routing_info() -> dict:
    """Safe-to-expose model map for /health and documentation."""
    return {
        "provider": "nebius-token-factory",
        "fast": {"model": settings.NEMOTRON_NANO_MODEL, "role": "extract messy sale reports"},
        "everyday": {"model": settings.NEMOTRON_SUPER_MODEL, "role": "picker chat + tools"},
        "reasoning": {"model": settings.NEMOTRON_ULTRA_MODEL, "role": "anomaly judgment only"},
        "regions": public_regions(),
    }
