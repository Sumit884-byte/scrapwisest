"""Keep only same-market, in-band public listings.

Web snippets never become a sale and never replace ``estimate_price``.
Social posts and foreign-currency numbers are dropped.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from app.core.config import settings

_BLOCKED_HOSTS = (
    "facebook.com",
    "fb.com",
    "m.facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "pinterest.com",
    "youtube.com",
    "youtu.be",
    "threads.net",
    "quora.com",
    "t.me",
    "whatsapp.com",
)

# Explicit per-kg amounts. Rs is resolved against the requested market.
_PRICE_PATTERNS = (
    re.compile(
        r"(?:pkr|inr|usd|eur|gbp|bdt|npr|rs\.?|₹|\$|€|£)\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:/|\s*per\s*)kg",
        re.I,
    ),
    re.compile(
        r"([0-9]+(?:\.[0-9]+)?)\s*"
        r"(?:pkr|inr|usd|eur|gbp|bdt|npr|rs\.?|₹|\$|€|£)\s*(?:/|\s*per\s*)kg",
        re.I,
    ),
)

_GENERIC_LO = 0.01
_GENERIC_HI = 100_000.0

TAVILY_EXCLUDE_DOMAINS = [
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "pinterest.com",
    "youtube.com",
    "threads.net",
]


def _host(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def is_blocked_host(url: str) -> bool:
    host = _host(url)
    return any(host == blocked or host.endswith("." + blocked) for blocked in _BLOCKED_HOSTS)


def _blob(*parts: str) -> str:
    return " ".join(p for p in parts if p).lower()


def mentions_place(text: str, country: str, city: str) -> bool:
    hay = text.lower()
    country_l = (country or "").strip().lower()
    city_l = (city or "").strip().lower()
    if city_l and city_l != "unknown" and city_l in hay:
        return True
    if country_l and country_l != "unknown" and country_l in hay:
        return True
    return False


def _rs_matches_request(currency: str, country: str, hay: str) -> bool:
    cur = (currency or "").strip().upper()
    country_l = (country or "").strip().lower()
    if not re.search(r"\brs\.?\b", hay):
        return False
    if "inr" in hay or "₹" in hay:
        return cur == "INR"
    if "pkr" in hay:
        return cur == "PKR"
    if cur == "PKR":
        return country_l in {"", "pakistan"} or "pakistan" in hay
    if cur == "INR":
        return country_l in {"", "india"} or "india" in hay
    return False


def mentions_currency(text: str, currency: str, country: str) -> bool:
    hay = text.lower()
    cur = (currency or "").strip().upper()
    if cur == "PKR":
        if re.search(r"\bpkr\b", hay) or "₨" in text:
            return True
        return _rs_matches_request(currency, country, hay)
    if cur == "INR":
        if "₹" in text or re.search(r"\binr\b", hay):
            return True
        return _rs_matches_request(currency, country, hay)
    if cur == "USD":
        return "$" in text or bool(re.search(r"\b(?:usd|us\$)\b", hay))
    if cur == "EUR":
        return "€" in text or bool(re.search(r"\beur\b", hay))
    if cur == "GBP":
        return "£" in text or bool(re.search(r"\bgbp\b", hay))
    if cur == "BDT":
        return bool(re.search(r"\b(?:bdt|tk)\b", hay))
    if cur == "NPR":
        return bool(re.search(r"\bnpr\b", hay))
    if cur and cur != "UNKNOWN":
        return bool(re.search(rf"\b{re.escape(cur.lower())}\b", hay))
    return False


def _token_matches_currency(token: str, currency: str, country: str, full_text: str) -> bool:
    cur = (currency or "").strip().upper()
    low = token.lower()
    hay = (full_text or "").lower()
    if "inr" in low or "₹" in token:
        return cur == "INR"
    if "pkr" in low or "₨" in token:
        return cur == "PKR"
    if "$" in token or "usd" in low:
        return cur == "USD"
    if "€" in token or "eur" in low:
        return cur == "EUR"
    if "£" in token or "gbp" in low:
        return cur == "GBP"
    if "bdt" in low or re.search(r"\btk\b", low):
        return cur == "BDT"
    if "npr" in low:
        return cur == "NPR"
    if "rs" in low:
        return _rs_matches_request(currency, country, hay if hay else low)
    return cur.lower() in low


def extract_prices(text: str, currency: str, material: str, country: str) -> list[float]:
    band = settings.price_band_for(material, country, currency)
    found: list[float] = []
    body = text or ""
    for pattern in _PRICE_PATTERNS:
        for match in pattern.finditer(body):
            try:
                value = float(match.group(1))
            except (TypeError, ValueError):
                continue
            if not _token_matches_currency(match.group(0), currency, country, body):
                continue
            if band is not None:
                if not (band[0] <= value <= band[1]):
                    continue
            elif not (_GENERIC_LO <= value <= _GENERIC_HI):
                continue
            found.append(value)
    return found


def reliable_web_context(
    raw: dict[str, Any],
    *,
    currency: str,
    country: str,
    city: str = "",
    material: str = "",
) -> dict[str, Any]:
    """Return filtered snippets/urls. Empty if nothing is market-safe."""
    kept: list[dict[str, str]] = []
    prices: list[float] = []
    for row in raw.get("results") or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        title = str(row.get("title") or "").strip()
        content = str(row.get("content") or "").strip()
        if not url or is_blocked_host(url):
            continue
        text = _blob(title, content, url)
        place_ok = mentions_place(text, country, city)
        currency_ok = mentions_currency(text, currency, country)
        extracted = extract_prices(f"{title} {content}", currency, material, country)
        if not extracted:
            continue
        if not place_ok and not currency_ok:
            continue
        kept.append({"title": title, "content": content, "url": url})
        prices.extend(extracted)

    if not kept:
        return {"context": None, "sources": [], "prices": [], "results": []}

    def _fmt(value: float) -> str:
        return f"{value:.2f}" if value < 10 else f"{value:.0f}"

    bits = [
        f"Public listings in {currency} (not a logged sale): "
        f"{_fmt(min(prices))}–{_fmt(max(prices))}/kg"
    ]

    return {
        "context": " ".join(bits)[:500],
        "sources": [row["url"] for row in kept[:3]],
        "prices": prices,
        "results": kept,
    }
