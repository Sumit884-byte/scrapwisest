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
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.market import (
    UNKNOWN_CURRENCY,
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


class ReportTrustStatus(str, Enum):
    """Canonical report trust lifecycle (Step 8).

    - PENDING: flagged/suspicious, stored for review, NEVER market data.
    - ACCEPTED: explicitly trusted, eligible for estimation/anomaly history.
    - REJECTED: reviewed and rejected, stored for audit, NEVER market data.

    This is distinct from any sale/business status. Trust status is the
    single authority for market-data eligibility; ``needs_confirmation``
    is a legacy-compatible derived flag (True <=> PENDING) kept in sync
    by the validator below so old payloads and old DB rows keep working.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


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

    @field_validator("country", "city", "neighborhood", "location_text", mode="before")
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
    trust_status: ReportTrustStatus = Field(default=ReportTrustStatus.ACCEPTED)
    needs_confirmation: bool = False
    confirmation_reason: Optional[str] = None
    picker_id: Optional[str] = None

    @model_validator(mode="after")
    def _sync_trust_status(self):
        """Keep one canonical trust state (Step 8).

        - ``needs_confirmation=True`` (legacy) implies PENDING.
        - PENDING implies ``needs_confirmation=True``.
        - ACCEPTED implies ``needs_confirmation=False``.
        - REJECTED is decided: ``needs_confirmation=False``.

        Legacy handling (§26): rows persisted before Step 8 have no
        ``trust_status`` and default to ACCEPTED here. That is correct for
        the main ``reports`` table, which historically only ever stored
        validated non-anomalous reports. Legacy ``pending_reports`` rows
        (which always had ``needs_confirmation=True``) are corrected to
        PENDING below instead of being silently declared accepted.
        """
        raw_status = self.trust_status
        status_val = (
            raw_status.value if isinstance(raw_status, Enum) else str(raw_status or "")
        ).strip().lower()
        needs = bool(self.needs_confirmation)

        if status_val == ReportTrustStatus.REJECTED.value:
            # Decided -- never needs confirmation.
            object.__setattr__(self, "trust_status", ReportTrustStatus.REJECTED.value)
            object.__setattr__(self, "needs_confirmation", False)
        elif needs:
            # Legacy flag wins: anything needing confirmation is PENDING,
            # never silently ACCEPTED.
            object.__setattr__(self, "trust_status", ReportTrustStatus.PENDING.value)
            object.__setattr__(self, "needs_confirmation", True)
        elif status_val == ReportTrustStatus.PENDING.value:
            # Explicit PENDING without the flag -- fix the flag.
            object.__setattr__(self, "trust_status", ReportTrustStatus.PENDING.value)
            object.__setattr__(self, "needs_confirmation", True)
        else:
            # ACCEPTED (including legacy default) with no flag -- canonical.
            object.__setattr__(self, "trust_status", ReportTrustStatus.ACCEPTED.value)
            object.__setattr__(self, "needs_confirmation", False)
        return self

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

    def market_key(self) -> tuple:
        """Identity of the market this report belongs to.

        Reports must never be pooled across different market keys --
        500 PKR and 500 INR are completely different monetary values.

        Delegates to :func:`app.schemas.market.market_key` (country +
        currency) and appends the city scope, so there is exactly one
        market-key normalization in the codebase.
        """
        cur, country = market_key(self.country, self.currency)
        return (
            cur,
            country,
            (self.city or "").strip().lower(),
        )


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

    @field_validator("country", "city", "neighborhood", mode="before")
    @classmethod
    def _normalize_place(cls, v):
        if v is None:
            return None
        return normalize_place_part(v if isinstance(v, str) else str(v))


class ReportResponse(PriceReport):
    """Response DTO for report queries."""
    id: Optional[int] = None
