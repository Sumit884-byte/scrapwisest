"""
Tool function for price estimation registered with DeepAgents/LangGraph.
"""

from __future__ import annotations

from typing import Union
from app.agent.tool_outputs import record_price
from app.schemas.market import resolve_currency
from app.schemas.price import PriceEstimate
from app.services.price_estimator import price_estimator_service


def estimate_price(
    material_str: str,
    location: str,
    currency: str = "",
    country: str = "",
    city: str = "",
) -> Union[PriceEstimate, dict]:
    """
    Estimate scrap price per kg for a material in a neighborhood.

    Use the picker's [picker_currency] and [picker_place: City, Country] when
    the message did not name a market. Quote estimated_price_per_kg in that
    currency. Never convert between currencies. Never mention confidence or tier.
    Use location "unknown" when the picker has not named an area.
    """
    code = resolve_currency(currency, None, country)
    result = price_estimator_service.estimate_price(
        material_str,
        location,
        currency=code,
        country=country or None,
        city=city or None,
    )
    if isinstance(result, PriceEstimate):
        record_price(result)
        return result.model_dump(mode="json")
    return result
