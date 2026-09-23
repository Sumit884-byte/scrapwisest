"""Deterministic normalization for informal neighborhood names.

Also hosts the market-agnostic helpers for the global report model.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from app.schemas.market import (
    MAX_PLACE_PART_LEN,
    UNKNOWN_CURRENCY,
    canonicalize_country,
    is_plausible_currency,
    market_key,
    normalize_currency,
    normalize_place_part,
    parse_place_label,
    resolve_currency,
)

__all__ = [
    "normalize_location",
    "MAX_PLACE_PART_LEN",
    "UNKNOWN_CURRENCY",
    "is_plausible_currency",
    "normalize_currency",
    "normalize_place_part",
    "canonicalize_country",
    "parse_place_label",
    "resolve_currency",
    "market_key",
    "picker_place_from_tags",
    "picker_currency_from_tags",
    "picker_neighborhood_from_tags",
    "validate_market_fields",
]


_ALIASES = {
    "income colony": "Income Colony",
    "samejabad": "Samejabad",
    "sameja abad": "Samejabad",
    "bosan road": "Bosan Road",
    "bosan rd": "Bosan Road",
    "bosan rood": "Bosan Road",
    "mumtazabad": "Mumtazabad",
    "mumtaz abad": "Mumtazabad",
    "karol bagh": "Karol Bagh",
    "pilsen": "Pilsen",
}


def normalize_location(value: str | None) -> str:
    """Return a stable area label without assuming one city."""
    if not value:
        return "unknown"

    text = re.sub(r"\s+", " ", value.strip().lower())
    text = re.sub(r"\b(?:near|around|close to|ke qareeb|kay qareeb)\b", "", text)
    text = re.sub(r"[,\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return "unknown"

    if text in _ALIASES:
        return _ALIASES[text]

    for alias, canonical in _ALIASES.items():
        if text == alias or text.startswith(alias + " ") or text.endswith(" " + alias):
            return canonical

    return text.title()


_PICKER_PLACE_RE = re.compile(r"\[picker_place:\s*([^\]]+)\]", re.IGNORECASE)
_PICKER_CURRENCY_RE = re.compile(r"\[picker_currency:\s*([^\]]+)\]", re.IGNORECASE)
_PICKER_NEIGHBORHOOD_RE = re.compile(r"\[picker_neighborhood:\s*([^\]]+)\]", re.IGNORECASE)


def picker_place_from_tags(message: str | None) -> Tuple[Optional[str], Optional[str]]:
    """Parse ``[picker_place: City, Country]`` back into (city, country)."""
    match = _PICKER_PLACE_RE.search(message or "")
    if not match:
        return (None, None)
    return parse_place_label(match.group(1))


def picker_currency_from_tags(message: str | None) -> Optional[str]:
    """Parse ``[picker_currency: XXX]`` back into a normalized code."""
    match = _PICKER_CURRENCY_RE.search(message or "")
    if not match:
        return None
    return normalize_currency(match.group(1))


def picker_neighborhood_from_tags(message: str | None) -> Optional[str]:
    """Parse ``[picker_neighborhood: ...]`` back into a neighborhood name."""
    match = _PICKER_NEIGHBORHOOD_RE.search(message or "")
    if not match:
        return None
    return normalize_place_part(match.group(1))


def validate_market_fields(
    currency: str | None,
    country: str | None,
    city: str | None,
    neighborhood: str | None,
) -> list:
    """Deterministic validation for the structured market fields."""
    reasons: list = []
    normalized = normalize_currency(currency)
    if not is_plausible_currency(normalized):
        reasons.append(f"unrecognized currency '{(currency or '').strip()}'")
    for label, part in (
        ("country", country),
        ("city", city),
        ("neighborhood", neighborhood),
    ):
        text = (part or "").strip()
        if text and len(text) > MAX_PLACE_PART_LEN:
            reasons.append(f"{label} name too long (max {MAX_PLACE_PART_LEN} characters)")
    return reasons
