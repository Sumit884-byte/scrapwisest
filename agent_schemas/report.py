from datetime import datetime, timezone
from enum import Enum
from typing import Optional, TypedDict

from pydantic import BaseModel, Field

class MaterialType(str, Enum):
    PLASTIC_PET = "plastic_pet"
    PLASTIC_HDPE = "plastic_hdpe"
    GLASS = "glass"
    METAL_ALUMINUM = "metal_aluminum"
    METAL_STEEL = "metal_steel"
    CARDBOARD = "cardboard"
    MIXED_PAPER = "mixed_paper"
    OTHER = "other"



class RawExtraction(BaseModel):
    """What the LLM returns, before any validation."""

    material_type: MaterialType
    material_confidence: float = Field(ge=0.0, le=1.0)
    quantity_kg: Optional[float] = Field(default=None, ge=0.0)
    quantity_confidence: float = Field(ge=0.0, le=1.0)
    price_paid_pkr: Optional[float] = Field(default=None, ge=0.0)
    price_confidence: float = Field(ge=0.0, le=1.0)
    location_text: Optional[str] = None
    unclear_fields: list[str] = Field(default_factory=list)


class PriceReport(BaseModel):
    """Final, validated report -- this is what the anomaly agent receives."""

    material_type: MaterialType
    quantity_kg: float
    price_paid_pkr: float
    price_paid_pkr_per_kg: float
    location: str
    timestamp: datetime
    reported_by: str
    needs_confirmation: bool = False
    confirmation_reason: Optional[str] = None