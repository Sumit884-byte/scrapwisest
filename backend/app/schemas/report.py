"""
Pydantic models and schemas for scrap sale reports, extraction, and anomaly verdicts.

The data model is market-agnostic: money is always a (total_price, currency)
pair and place is always (country, city, neighborhood). No market, country,
or currency is hardcoded into the schema.

Backwards compatibility: the legacy ``price_paid_pkr`` /
``price_paid_pkr_per_kg`` names are still accepted on input (old rows and old
API payloads keep parsing) but everything is stored and emitted under the
generic ``total_price`` / ``price_per_kg`` names. Legacy rows that never
named a currency parse as ``currency="unknown"`` -- never a guessed code.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.schemas.market import (
    UNKNOWN_CURRENCY,
    canonicalize_country,
    market_key,
    normalize_currency,
    normalize_place_part,
)


class MaterialType(str, Enum):
    PLASTIC_PET = "plastic_pet"
    PLASTIC_HDPE = "plastic_hdpe"
    GLASS = "glass"
    METAL_ALUMINUM = "metal_aluminum"
    METAL_STEEL = "metal_steel"
    CARDBOARD = "cardboard"
    MIXED_PAPER = "mixed_paper"
    OTHER = "other"


def _total_price_alias() -> AliasChoices:
    # Canonical name first: OpenAPI / LLM structured-output schemas show
    # "total_price" while old payloads using "price_paid_pkr" still parse.
    return AliasChoices("total_price", "price_paid_pkr")


def _price_per_kg_alias() -> AliasChoices:
    return AliasChoices("price_per_kg", "price_paid_pkr_per_kg")


class RawExtraction(BaseModel):
    """What the extraction LLM returns, before any validation."""
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    material_type: MaterialType
    material_confidence: float = Field(ge=0.0, le=1.0)
    quantity_kg: Optional[float] = Field(default=None, ge=0.0)
    quantity_confidence: float = Field(ge=0.0, le=1.0)
    total_price: Optional[float] = Field(
        default=None, ge=0.0, validation_alias=_total_price_alias()
    )
    price_confidence: float = Field(ge=0.0, le=1.0)
    currency: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    location_text: Optional[str] = None
    unclear_fields: list[str] = Field(default_factory=list)

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, v):
        if v is None:
            return None
        return normalize_currency(v if isinstance(v, str) else str(v))

    @field_validator("country", mode="before")
    @classmethod
    def _normalize_country(cls, v):
        if v is None:
            return None
        return canonicalize_country(v if isinstance(v, str) else str(v))

    @field_validator("city", "neighborhood", "location_text", mode="before")
    @classmethod
    def _normalize_place(cls, v):
        if v is None:
            return None
        return normalize_place_part(v if isinstance(v, str) else str(v))


class PriceReport(BaseModel):
    """Validated intake output -- also the input the anomaly tiers score."""
    model_config = ConfigDict(
        use_enum_values=True, from_attributes=True, populate_by_name=True
    )

    material_type: MaterialType
    quantity_kg: float
    total_price: float = Field(validation_alias=_total_price_alias())
    price_per_kg: float = Field(validation_alias=_price_per_kg_alias())
    currency: str = UNKNOWN_CURRENCY
    country: Optional[str] = None
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    location: str = "unknown"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    needs_confirmation: bool = False
    confirmation_reason: Optional[str] = None
    picker_id: Optional[str] = None

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, v):
        if v is None:
            return UNKNOWN_CURRENCY
        return normalize_currency(v if isinstance(v, str) else str(v))

    @field_validator("country", mode="before")
    @classmethod
    def _normalize_country(cls, v):
        if v is None:
            return None
        return canonicalize_country(v if isinstance(v, str) else str(v))

    @field_validator("city", "neighborhood", mode="before")
    @classmethod
    def _normalize_place(cls, v):
        if v is None:
            return None
        return normalize_place_part(v if isinstance(v, str) else str(v))

    def market_key(self) -> tuple:
        """Identity of the market this report belongs to.

        Reports must never be pooled across different market keys --
        500 PKR and 500 INR are completely different monetary values.
        """
        return market_key(self.currency, self.country, self.city)


class AnomalyVerdict(BaseModel):
    """Outcome of anomaly detection evaluation."""
    model_config = ConfigDict(use_enum_values=True)

    is_anomalous: bool
    reason: str
    method: str  # "deterministic" | "ml" | "llm"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class LLMJudgment(BaseModel):
    """Schema the LLM judge fills in."""
    is_anomalous: bool
    reason: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)


class ReportCreate(BaseModel):
    """Payload for manually logging a report via REST API."""
    # NOTE: no use_enum_values here -- endpoints rely on
    # payload.material_type being a MaterialType member (.value access).
    model_config = ConfigDict(populate_by_name=True)

    material_type: MaterialType
    quantity_kg: float = Field(gt=0.0)
    total_price: float = Field(gt=0.0, validation_alias=_total_price_alias())
    currency: str = UNKNOWN_CURRENCY
    country: Optional[str] = None
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    location: str = Field(min_length=1)
    picker_id: Optional[str] = None

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, v):
        if v is None:
            return UNKNOWN_CURRENCY
        return normalize_currency(v if isinstance(v, str) else str(v))

    @field_validator("country", mode="before")
    @classmethod
    def _normalize_country(cls, v):
        if v is None:
            return None
        return canonicalize_country(v if isinstance(v, str) else str(v))

    @field_validator("city", "neighborhood", mode="before")
    @classmethod
    def _normalize_place(cls, v):
        if v is None:
            return None
        return normalize_place_part(v if isinstance(v, str) else str(v))


class ReportResponse(PriceReport):
    """Response DTO for report queries."""
    id: Optional[int] = None
