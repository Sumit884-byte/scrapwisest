from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# --------
# schemas
# --------

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
    """What the extraction LLM returns, before any validation."""

    material_type: MaterialType
    material_confidence: float = Field(ge=0.0, le=1.0)
    quantity_kg: Optional[float] = Field(default=None, ge=0.0)
    quantity_confidence: float = Field(ge=0.0, le=1.0)
    price_paid_pkr: Optional[float] = Field(default=None, ge=0.0)
    price_confidence: float = Field(ge=0.0, le=1.0)
    location_text: Optional[str] = None
    unclear_fields: list[str] = Field(default_factory=list)


class PriceReport(BaseModel):
    """Validated intake output -- also the input the anomaly tiers score."""

    material_type: MaterialType
    quantity_kg: float
    price_paid_pkr: float
    price_paid_pkr_per_kg: float
    location: str
    timestamp: datetime
    needs_confirmation: bool = False
    confirmation_reason: Optional[str] = None


class AnomalyVerdict(BaseModel):
    is_anomalous: bool
    reason: str
    method: str  # "deterministic" | "ml" | "llm"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class LLMJudgment(BaseModel):
    """Schema the LLM judge fills in -- method gets added back on by
    llm_check_node() once we have this."""

    is_anomalous: bool
    reason: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)