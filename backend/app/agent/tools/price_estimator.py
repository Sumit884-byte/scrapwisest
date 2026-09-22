"""
Tool function for price estimation registered with DeepAgents/LangGraph.
"""

from __future__ import annotations

from typing import Union
from app.agent.tool_outputs import record_price
from app.schemas.price import PriceEstimate
from app.services.price_estimator import price_estimator_service


def estimate_price(material_str: str, location: str) -> Union[PriceEstimate, dict]:
    """
    Estimate scrap price per kg (PKR, not INR) for a material in a neighborhood.
    Use location "unknown" when the picker has not named an area.
    Quote only estimated_price_per_kg as Pakistani rupees per kg. Never mention confidence or tier.
    """
    result = price_estimator_service.estimate_price(material_str, location)
    if isinstance(result, PriceEstimate):
        record_price(result)
        return result.model_dump(mode="json")
    return result
