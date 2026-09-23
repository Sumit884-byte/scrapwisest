"""
Market-agnostic primitives for the global report model.

Money is always a (total_price, currency) pair and place is always
(country, city, neighborhood). No single market is assumed at the call site.

This module has no intra-project imports on purpose: schema modules and
service modules both depend on it, so it must never depend on them
(import cycle safety).
"""

from __future__ import annotations

import re
from typing import Optional

UNKNOWN_CURRENCY = "unknown"

MAX_PLACE_PART_LEN = 64

# ISO 4217 codes we actually quote. Anything else must be confirmed.
KNOWN_CURRENCIES = frozenset(
    {
        "PKR",
        "INR",
        "USD",
        "BDT",
        "NPR",
        "EUR",
        "GBP",
        "AED",
        "SAR",
        "LKR",
        "AFN",
    }
)

_COUNTRY_ALIASES = {
    "pakistan": "Pakistan",
    "india": "India",
    "bharat": "India",
    "hindustan": "India",
    "bangladesh": "Bangladesh",
    "nepal": "Nepal",
    "united states": "United States",
    "united states of america": "United States",
    "usa": "United States",
    "us": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "america": "United States",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
}

_COUNTRY_CURRENCY = {
    "Pakistan": "PKR",
    "India": "INR",
    "Bangladesh": "BDT",
    "Nepal": "NPR",
    "United States": "USD",
    "United Kingdom": "GBP",
}

_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")


def normalize_currency(value: str | None) -> str:
    """Uppercase/strip a currency code; fall back to ``UNKNOWN_CURRENCY``."""
    text = (value or "").strip()
    if not text or text.upper() == UNKNOWN_CURRENCY.upper():
        return UNKNOWN_CURRENCY
    return text.upper()


def is_unknown_currency(code: str | None) -> bool:
    return normalize_currency(code) == UNKNOWN_CURRENCY


def is_known_currency(code: str | None) -> bool:
    normalized = normalize_currency(code)
    return normalized in KNOWN_CURRENCIES


def is_plausible_currency(code: str | None) -> bool:
    """True for unknown, a known ISO code, or (legacy) any 3-letter code.

    Known codes are preferred. Unknown is allowed. Random 3-letter tokens
    such as FOO are rejected.
    """
    if not code or is_unknown_currency(code):
        return True
    normalized = normalize_currency(code)
    if normalized in KNOWN_CURRENCIES:
        return True
    # Reject non-ISO junk (FOO, RUP, XYZ) even if it is 3 letters.
    return False


def normalize_place_part(value: str | None) -> Optional[str]:
    """Strip a country/city/neighborhood part; empty becomes None."""
    text = (value or "").strip()
    return text or None


def _fold_country(value: str | None) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip().lower())
    text = text.replace(".", "")
    return text


def canonicalize_country(value: str | None) -> Optional[str]:
    """Map USA/US/Bharat/… onto one country label. Unknown text is kept."""
    folded = _fold_country(value)
    if not folded:
        return None
    if folded in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[folded]
    return normalize_place_part(value)


def normalize_country_key(value: str | None) -> str:
    canonical = canonicalize_country(value)
    return (canonical or "").strip().lower()


def normalize_city_key(value: str | None) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip().lower())
    return text


def currency_for_country(country: str | None) -> Optional[str]:
    canonical = canonicalize_country(country)
    if not canonical:
        return None
    return _COUNTRY_CURRENCY.get(canonical)


def coalesce_currency(*candidates: str | None) -> str:
    """First real currency wins; unknown/empty is skipped."""
    for candidate in candidates:
        if candidate is None:
            continue
        normalized = normalize_currency(candidate)
        if not is_unknown_currency(normalized):
            return normalized
    return UNKNOWN_CURRENCY


def resolve_currency(
    extracted: str | None = None,
    tagged: str | None = None,
    country: str | None = None,
) -> str:
    """Explicit extraction, then picker tag, then country default."""
    return coalesce_currency(extracted, tagged, currency_for_country(country))


def parse_place_label(text: str | None) -> tuple[Optional[str], Optional[str]]:
    """Split ``City, Country`` or ``City, Region, Country`` into (city, country).

    The last segment is the country when it matches a known country alias.
    Otherwise a single comma split is used (city, rest-as-country).
    """
    raw = (text or "").strip()
    if not raw:
        return (None, None)
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not parts:
        return (None, None)
    last = canonicalize_country(parts[-1])
    last_is_known = _fold_country(parts[-1]) in _COUNTRY_ALIASES
    if last_is_known and len(parts) == 1:
        return (None, last)
    if last_is_known:
        city = ", ".join(parts[:-1]) or None
        return (city, last)
    if len(parts) == 1:
        return (parts[0], None)
    return (parts[0], ", ".join(parts[1:]) or None)


def market_key(
    currency: str | None,
    country: str | None,
    city: str | None,
) -> tuple[str, str, str]:
    """Identity used to pool reports. Never mix different keys."""
    return (
        normalize_currency(currency),
        normalize_country_key(country),
        normalize_city_key(city),
    )


def currency_label(code: str | None) -> str:
    normalized = normalize_currency(code)
    if is_unknown_currency(normalized):
        return ""
    return normalized
