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
