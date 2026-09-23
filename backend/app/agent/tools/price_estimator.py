"""
Tool function for price estimation registered with DeepAgents/LangGraph.
"""

from __future__ import annotations

from typing import Union
from app.agent.tool_outputs import record_price
from app.schemas.price import PriceEstimate
from app.services.price_estimator import price_estimator_service


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
    result = price_estimator_service.estimate_price(
        material_str, location, currency, country, city, neighborhood
    )
    if isinstance(result, PriceEstimate):
        record_price(result)
        return result.model_dump(mode="json")
    return result
