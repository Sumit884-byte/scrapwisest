"""
Tool function for price estimation registered with DeepAgents/LangGraph.
"""

from __future__ import annotations

from typing import Union
from app.agent.tool_outputs import record_price
from app.schemas.price import PriceEstimate
from app.services.price_estimator import price_estimator_service


def _is_missing(value: str | None) -> bool:
    return not (value or "").strip() or (value or "").strip().lower() == "unknown"


def estimate_price(
    material_str: str,
    location: str,
    currency: str = "unknown",
    country: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
) -> Union[PriceEstimate, dict]:
    """
    Estimate scrap price per kg in the picker's local market and currency.
    Use the user's local market and currency. Do not assume PKR. Do not
    convert currencies unless a dedicated currency-conversion feature exists.
    Use location "unknown" when the picker has not named an area.
    Quote only estimated_price_per_kg in the estimate's own currency per kg.
    Never mention confidence or tier.
    """
    # Same canonical picker context as the report pipeline: explicit tool
    # args win, picker defaults backfill the rest (no guessing, no
    # cross-market contamination). This keeps one location context for the
    # report and the estimator instead of two diverging ones.
    try:
        from app.agent.tool_outputs import get_market_context
        from app.services.location_resolver import resolve_market_context

        slot = get_market_context() or {}
        resolved = resolve_market_context(
            explicit_country=None if _is_missing(country) else country,
            explicit_currency=None if _is_missing(currency) else currency,
            explicit_city=None if _is_missing(city) else city,
            explicit_neighborhood=(
                None if _is_missing(neighborhood) else neighborhood
            ),
            picker_country=slot.get("country"),
            picker_currency=slot.get("currency"),
            picker_city=slot.get("city"),
            picker_neighborhood=slot.get("neighborhood"),
        )
        currency = resolved.currency
        country = resolved.country
        city = resolved.city
        neighborhood = resolved.neighborhood
        if _is_missing(location) and (neighborhood or city):
            location = neighborhood or city or location
    except Exception:
        pass
    result = price_estimator_service.estimate_price(
        material_str, location, currency, country, city, neighborhood
    )
    if isinstance(result, PriceEstimate):
        record_price(result)
        return result.model_dump(mode="json")
    return result
