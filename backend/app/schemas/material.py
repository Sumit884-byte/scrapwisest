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
    seed_price_pkr_per_kg: float
    price_band_pkr: Tuple[float, float]


class MaterialListResponse(BaseModel):
    materials: List[MaterialInfo]
    count: int
