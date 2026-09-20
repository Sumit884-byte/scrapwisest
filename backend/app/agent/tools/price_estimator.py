"""
Tool function for price estimation registered with DeepAgents/LangGraph.
"""

from __future__ import annotations

from typing import Union
from app.schemas.price import PriceEstimate
from app.services.price_estimator import price_estimator_service


def estimate_price(material_str: str, location: str) -> Union[PriceEstimate, dict]:
    """
    Estimate scrap price per kg for a given material type in a specific location or neighborhood.
    Returns estimated price per kg, confidence score, and regional sample statistics.
    """
    return price_estimator_service.estimate_price(material_str, location)
