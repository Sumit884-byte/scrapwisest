"""
Market-agnostic primitives for the global report model.

Money is always a (total_price, currency) pair and place is always
(country, city, neighborhood). No market, country, or currency is
hardcoded here.

This module has no intra-project imports on purpose: schema modules and
service modules both depend on it, so it must never depend on them
(import cycle safety).
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, field_validator

#: Sentinel for "we genuinely don't know". Legacy rows and messages that
#: never named a currency land here instead of a guessed code.
UNKNOWN_CURRENCY = "unknown"

#: Plausible currency codes are 3-letter codes (ISO 4217 style: PKR, INR, USD).
_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")

#: Longest accepted country/city/neighborhood string. Longer values are
#: flagged for picker confirmation instead of being silently truncated.
MAX_PLACE_PART_LEN = 64


def normalize_currency(value: str | None) -> str:
    """Uppercase/strip a currency code; fall back to ``UNKNOWN_CURRENCY``."""
    text = (value or "").strip()
    if not text or text.upper() == UNKNOWN_CURRENCY.upper():
        return UNKNOWN_CURRENCY
    return text.upper()


def is_plausible_currency(code: str | None) -> bool:
    """True for ``UNKNOWN_CURRENCY`` or a 3-letter code (PKR, INR, USD, ...)."""
    if not code:
        return True
    normalized = code.strip().upper()
    return normalized == UNKNOWN_CURRENCY.upper() or bool(_CURRENCY_RE.match(normalized))


def normalize_place_part(value: str | None) -> Optional[str]:
    """Strip a country/city/neighborhood part; empty becomes None."""
    text = (value or "").strip()
    return text or None


def market_key(country: str | None, currency: str | None) -> tuple[str, str]:
    """Canonical market identity: ``(currency, country)``.

    Both parts use the same normalization as every report
    (``normalize_currency`` + case-folded ``normalize_place_part``) so there
    is exactly one market-key implementation in the codebase. Currency alone
    is never the full identity -- a market is always country + currency
    (e.g. ``("PKR", "pakistan")``). Missing country normalizes to ``""``
    (the legacy/unknown market).
    """
    cur = normalize_currency(currency)
    part = normalize_place_part(country)
    return (cur, (part or "").lower())


#: Well-known (country -> currency) pairs used ONLY to flag obvious
#: country/currency mismatches (e.g. India + PKR) for picker confirmation.
#: Anything not listed here is never flagged -- we never guess, convert,
#: or silently rewrite the user's transaction.
KNOWN_COUNTRY_CURRENCIES: dict[str, str] = {
    "pakistan": "PKR",
    "india": "INR",
    "bangladesh": "BDT",
    "nepal": "NPR",
    "united states": "USD",
    "usa": "USD",
    "us": "USD",
    "united kingdom": "GBP",
    "uk": "GBP",
    "france": "EUR",
    "germany": "EUR",
}


def expected_currency_for_country(country: str | None) -> Optional[str]:
    """Expected currency for a well-known country, or None when unknown."""
    part = normalize_place_part(country)
    if not part:
        return None
    return KNOWN_COUNTRY_CURRENCIES.get(part.lower())


def is_unknown_currency(code: str | None) -> bool:
    return normalize_currency(code) == UNKNOWN_CURRENCY


_COUNTRY_CANON = {
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
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
}


def canonicalize_country(value: str | None) -> Optional[str]:
    part = normalize_place_part(value)
    if not part:
        return None
    return _COUNTRY_CANON.get(part.lower(), part)


def resolve_currency(
    extracted: str | None = None,
    tagged: str | None = None,
    country: str | None = None,
) -> str:
    """Explicit extraction, then picker tag, then country default."""
    for candidate in (extracted, tagged, expected_currency_for_country(country)):
        if candidate is None:
            continue
        normalized = normalize_currency(candidate)
        if not is_unknown_currency(normalized):
            return normalized
    return UNKNOWN_CURRENCY


def market_consistency_reason(
    country: str | None, currency: str | None
) -> Optional[str]:
    """Return a human-readable reason when country + currency obviously clash.

    Only fires when BOTH values are explicitly known AND the country is a
    well-known market with a different expected currency. Missing/unknown
    values never flag -- we preserve the raw information and leave genuinely
    missing fields missing.
    """
    part = normalize_place_part(country)
    cur = normalize_currency(currency)
    if not part or cur == UNKNOWN_CURRENCY:
        return None
    expected = KNOWN_COUNTRY_CURRENCIES.get(part.lower())
    if expected is None or cur.upper() == expected:
        return None
    return (
        f"country/currency mismatch: {part} usually uses {expected}, "
        f"got {cur.upper()}"
    )


class MarketContext(BaseModel):
    """One canonical market/location context for picker settings.

    This is the single structured representation of
    ``country / currency / city / neighborhood`` used by chat intake,
    report validation, and price estimation. Do NOT create duplicate
    representations elsewhere -- reuse this model and the helpers in
    :mod:`app.services.location_resolver`.
    """

    country: Optional[str] = None
    currency: str = UNKNOWN_CURRENCY
    city: Optional[str] = None
    neighborhood: Optional[str] = None

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, v):
        if v is None:
            return UNKNOWN_CURRENCY
        return normalize_currency(v if isinstance(v, str) else str(v))

    @field_validator("country", "city", "neighborhood", mode="before")
    @classmethod
    def _normalize_place(cls, v):
        if v is None:
            return None
        return normalize_place_part(v if isinstance(v, str) else str(v))

    def is_empty(self) -> bool:
        """True when no market/location value is known at all."""
        return (
            self.country is None
            and self.city is None
            and self.neighborhood is None
            and normalize_currency(self.currency) == UNKNOWN_CURRENCY
        )
