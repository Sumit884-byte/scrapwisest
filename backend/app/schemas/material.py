"""
Pydantic schemas for material types and reference metadata.
"""

from __future__ import annotations

from typing import List, Tuple
from pydantic import BaseModel
from app.schemas.report import MaterialType


class MaterialInfo(BaseModel):
    id: str
    name_en: str
    name_ur: str
    name_te: str = ""
    seed_price_per_kg: float
    price_band_per_kg: Tuple[float, float]
    # Currency the seed price / band are denominated in. The current seeds
    # were collected in one market (PKR); per-market seeds land later.
    currency: str = "PKR"


class MaterialListResponse(BaseModel):
    materials: List[MaterialInfo]
    count: int
