"""Deterministic normalization for informal neighborhood names.

Also hosts the market-agnostic helpers for the global report model:
money is always a (total_price, currency) pair and place is always
(country, city, neighborhood). No market, country, or currency is
hardcoded here.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from app.schemas.market import (
    MAX_PLACE_PART_LEN,
    UNKNOWN_CURRENCY,
    MarketContext,
    is_plausible_currency,
    market_consistency_reason,
    market_key,
    normalize_currency,
    normalize_place_part,
)

__all__ = [
    "normalize_location",
    "MAX_PLACE_PART_LEN",
    "UNKNOWN_CURRENCY",
    "is_plausible_currency",
    "normalize_currency",
    "normalize_place_part",
    "market_key",
    "same_country",
    "same_city",
    "same_neighborhood",
    "neighborhood_label",
    "picker_place_from_tags",
    "picker_currency_from_tags",
    "picker_neighborhood_from_tags",
    "validate_market_fields",
    "resolve_market_context",
]


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
    """Return a stable neighborhood label while retaining unknown locations.

    Market-agnostic: no city or country name is hardcoded or stripped, so a
    city-only location such as ``"Multan"`` stays usable instead of
    collapsing to an empty string.
    """
    if not value or not value.strip():
        return "unknown"

    original = value.strip()
    text = re.sub(r"\s+", " ", original.lower())
    text = re.sub(r"\b(?:near|around|close to|ke qareeb|kay qareeb)\b", "", text)
    text = re.sub(r"[,\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        # The value was only filler words/punctuation -- keep the original
        # text instead of returning an empty label.
        return original.title()

    if text in _ALIASES:
        return _ALIASES[text]

    for alias, canonical in _ALIASES.items():
        if alias in text:
            return canonical

    return text.title()


def _fold_part(value: str | None) -> str:
    """Case-folded comparison key for a structured place part."""
    part = normalize_place_part(value)
    return (part or "").lower()


def same_country(first: str | None, second: str | None) -> bool:
    """True when two country values name the same country (case-insensitive)."""
    return _fold_part(first) == _fold_part(second)


def same_city(
    first_city: str | None,
    first_country: str | None,
    second_city: str | None,
    second_country: str | None,
) -> bool:
    """True only when BOTH city and country match.

    Comparing city names alone would confuse e.g. Springfield, USA with a
    Springfield elsewhere, so the country is always part of the comparison.
    """
    return _fold_part(first_city) == _fold_part(second_city) and same_country(
        first_country, second_country
    )


def neighborhood_label(neighborhood: str | None, location: str | None) -> Optional[str]:
    """Best-effort normalized neighborhood label, or None when unknown."""
    raw = (neighborhood or "").strip() or (location or "").strip()
    if not raw or raw.strip().lower() == "unknown":
        return None
    normalized = normalize_location(raw)
    if not normalized or normalized.strip().lower() == "unknown":
        return None
    return normalized


def same_neighborhood(
    first_neighborhood: str | None,
    first_city: str | None,
    first_country: str | None,
    first_location: str | None = None,
    second_neighborhood: str | None = None,
    second_city: str | None = None,
    second_country: str | None = None,
    second_location: str | None = None,
) -> bool:
    """True only when neighborhood AND city AND country all match.

    The city/country gate keeps an ``Income Colony`` in one city/country
    from matching an unrelated ``Income Colony`` elsewhere. Either the
    structured ``neighborhood`` field or the legacy free-text ``location``
    may supply the label.
    """
    if not same_city(first_city, first_country, second_city, second_country):
        return False
    first_label = neighborhood_label(first_neighborhood, first_location)
    second_label = neighborhood_label(second_neighborhood, second_location)
    if first_label is None or second_label is None:
        return False
    return first_label.lower() == second_label.lower()


# ---------------------------------------------------------------------------
# Picker-context tag parsers. Context tags appended to chat messages by the
# /chat endpoint carry the picker's *explicit* settings (never guesses) and
# are parsed back deterministically by the report pipeline.
# ---------------------------------------------------------------------------

_PICKER_PLACE_RE = re.compile(r"\[picker_place:\s*([^\]]+)\]", re.IGNORECASE)
_PICKER_CURRENCY_RE = re.compile(r"\[picker_currency:\s*([^\]]+)\]", re.IGNORECASE)
_PICKER_NEIGHBORHOOD_RE = re.compile(r"\[picker_neighborhood:\s*([^\]]+)\]", re.IGNORECASE)


def picker_place_from_tags(message: str | None) -> Tuple[Optional[str], Optional[str]]:
    """Parse ``[picker_place: City, Country]`` back into (city, country)."""
    match = _PICKER_PLACE_RE.search(message or "")
    if not match:
        return (None, None)
    parts = [part.strip() for part in match.group(1).split(",", 1)]
    city = parts[0] or None
    country = parts[1].strip() if len(parts) > 1 else None
    return (city, country or None)


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
    """Deterministic validation for the structured market fields.

    Returns a list of human-readable reasons; an empty list means the
    fields are acceptable. Nothing here guesses -- unparsable values are
    reported so the picker can confirm or correct them. Obvious
    country/currency clashes (e.g. India + PKR) are flagged for picker
    confirmation instead of being silently rewritten.
    """
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
    consistency = market_consistency_reason(country, currency)
    if consistency is not None:
        reasons.append(consistency)
    return reasons


def _explicit_currency(value: str | None) -> Optional[str]:
    """Normalized explicit currency, or None when missing/unknown."""
    if value is None:
        return None
    normalized = normalize_currency(value)
    if normalized == UNKNOWN_CURRENCY:
        return None
    return normalized


def resolve_market_context(
    explicit_country: str | None = None,
    explicit_currency: str | None = None,
    explicit_city: str | None = None,
    explicit_neighborhood: str | None = None,
    picker_country: str | None = None,
    picker_currency: str | None = None,
    picker_city: str | None = None,
    picker_neighborhood: str | None = None,
) -> MarketContext:
    """Merge explicit message/API values with picker defaults.

    Precedence (the single canonical rule for the whole codebase):

    - Case A (no explicit location): picker settings backfill every
      missing field.
    - Case B (explicit city): the explicit city wins and the stale picker
      neighborhood is dropped (it belonged to the old city). Country and
      currency still inherit from the picker when the message names no
      different country/currency.
    - Case C (explicit country/currency): explicit values win. When the
      explicit country differs from the picker country, picker city,
      neighborhood, AND currency are NOT inherited -- this prevents
      ``India / PKR`` or ``Delhi / Multan`` contamination. Currency is
      never guessed from words like "rupees" alone; genuinely missing
      stays ``unknown``.
    - Case D (ambiguous): explicit fields are None, so picker context is
      preserved and nothing is invented.

    Never invents a city/country/currency. Returns a normalized
    :class:`MarketContext`.
    """
    exp_country = normalize_place_part(explicit_country)
    exp_currency = _explicit_currency(explicit_currency)
    exp_city = normalize_place_part(explicit_city)
    exp_neighborhood = normalize_place_part(explicit_neighborhood)

    pick_country = normalize_place_part(picker_country)
    pick_currency = _explicit_currency(picker_currency)
    pick_city = normalize_place_part(picker_city)
    pick_neighborhood = normalize_place_part(picker_neighborhood)

    country_changed = bool(
        exp_country
        and pick_country
        and exp_country.lower() != pick_country.lower()
    )
    city_changed = bool(
        exp_city and pick_city and exp_city.lower() != pick_city.lower()
    )

    if exp_country:
        country = exp_country
    elif pick_country:
        country = pick_country
    else:
        country = None

    if exp_currency:
        currency = exp_currency
    elif country_changed:
        # Explicitly moved to a different country's market -- do not drag
        # the old market's currency along (avoids India/PKR).
        currency = UNKNOWN_CURRENCY
    elif pick_currency:
        currency = pick_currency
    else:
        currency = UNKNOWN_CURRENCY

    if exp_city:
        city = exp_city
    elif country_changed:
        # Old city belonged to the old country.
        city = None
    elif pick_city:
        city = pick_city
    else:
        city = None

    if exp_neighborhood:
        neighborhood = exp_neighborhood
    elif country_changed:
        neighborhood = None
    elif city_changed:
        # Old neighborhood belonged to the old city (keeps an
        # "Income Colony" in Multan from leaking into Lahore/Delhi).
        neighborhood = None
    elif pick_neighborhood:
        neighborhood = pick_neighborhood
    else:
        neighborhood = None

    return MarketContext(
        country=country,
        currency=currency,
        city=city,
        neighborhood=neighborhood,
    )
