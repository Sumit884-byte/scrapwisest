"""
Pydantic schemas for the chat endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.schemas.price import PriceEstimate
from app.schemas.report import MaterialType


class ReportReviewData(BaseModel):
    material_type: MaterialType
    quantity_kg: float
    price_paid_pkr: float
    price_paid_pkr_per_kg: float
    location: str
    needs_confirmation: bool = False
    confirmation_reason: Optional[str] = None
    is_anomalous: bool = False
    anomaly_reason: Optional[str] = None
    anomaly_method: Optional[str] = None


class ChatRequest(BaseModel):
    message: str = Field(default="", description="Text message from waste picker")
    picker_id: str = Field(..., description="Unique picker identifier")


class ChatResponse(BaseModel):
    reply: str
    history: List[Dict[str, Any]] = Field(default_factory=list)
    price_data: Optional[PriceEstimate] = Field(default=None)
    report_data: Optional[ReportReviewData] = Field(default=None)
