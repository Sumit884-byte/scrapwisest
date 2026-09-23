"""
Pydantic schemas for the chat endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from app.schemas.market import (
    UNKNOWN_CURRENCY,
    normalize_currency,
    normalize_place_part,
)
from app.schemas.price import PriceEstimate
from app.schemas.report import MaterialType


class ReportReviewData(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    material_type: MaterialType
    quantity_kg: float
    total_price: float = Field(
        validation_alias=AliasChoices("total_price", "price_paid_pkr")
    )
    price_per_kg: float = Field(
        validation_alias=AliasChoices("price_per_kg", "price_paid_pkr_per_kg")
    )
    currency: str = UNKNOWN_CURRENCY
    country: Optional[str] = None
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    location: str = "unknown"
    needs_confirmation: bool = False
    confirmation_reason: Optional[str] = None
    is_anomalous: bool = False
    anomaly_reason: Optional[str] = None
    anomaly_method: Optional[str] = None

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, v):
        if v is None:
            return UNKNOWN_CURRENCY
        return normalize_currency(v if isinstance(v, str) else str(v))

    @field_validator("country", "city", "neighborhood", mode="before")
    @classmethod
    def _normalize_place(cls, v):
        if v is None:
            return None
        return normalize_place_part(v if isinstance(v, str) else str(v))


class ChatRequest(BaseModel):
    message: str = Field(default="", description="Text message from waste picker")
    picker_id: str = Field(..., description="Unique picker identifier")


class ChatResponse(BaseModel):
    reply: str
    history: List[Dict[str, Any]] = Field(default_factory=list)
    price_data: Optional[PriceEstimate] = Field(default=None)
    report_data: Optional[ReportReviewData] = Field(default=None)
    region: Optional[str] = Field(default=None)
