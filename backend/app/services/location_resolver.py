"""Deterministic normalization for informal neighborhood names."""

from __future__ import annotations

import re


_ALIASES = {
    "income colony": "Income Colony",
    "income colony multan": "Income Colony",
    "samejabad": "Samejabad",
    "sameja abad": "Samejabad",
    "bosan road": "Bosan Road",
    "bosan rd": "Bosan Road",
    "bosan rood": "Bosan Road",
    "mumtazabad": "Mumtazabad",
    "mumtaz abad": "Mumtazabad",
}


def normalize_location(value: str | None) -> str:
    """Return a stable neighborhood label while retaining unknown locations."""
    if not value:
        return "unknown"

    text = re.sub(r"\s+", " ", value.strip().lower())
    text = re.sub(r"\b(?:near|around|close to|ke qareeb|kay qareeb)\b", "", text)
    text = re.sub(r"[,\-]+", " ", text)
    text = re.sub(r"\bmultan\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    if text in _ALIASES:
        return _ALIASES[text]

    for alias, canonical in _ALIASES.items():
        if alias in text:
            return canonical

    return text.title()
