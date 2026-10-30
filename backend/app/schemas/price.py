"""
Pydantic schemas for price estimation requests and responses.
"""

from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from app.schemas.market import UNKNOWN_CURRENCY
from app.schemas.report import MaterialType


class PriceEvidence(BaseModel):
    """Explainable provenance for one price estimate (Step 9).

    Answers: did this number come from real reports, a verified seed, or
    no data? What geographic scope actually produced it? How many eligible
    reports supported it? Which canonical market was used? Which freshness
    window was applied?

    Eligibility (single rule, same population the estimator prices from)::

        ACCEPTED + FRESH + same material + same market (market_key) +
        appropriate geographic scope

    PENDING, REJECTED, stale, and foreign-market reports never contribute
    to ``report_count``, ``confidence``, or the estimate value.

    Scope mirrors the estimator hierarchy (no second hierarchy)::

        tier "local"      -> scope "neighborhood"
        tier "local+city" -> scope "neighborhood+city" (blended medians;
                             report_count is the distinct city pool, which
                             already contains the neighborhood subset --
                             pools are nested, never summed)
        tier "city"       -> scope "city"
        tier "country"    -> scope "country"
        tier "seed"       -> scope "seed" (report_count is always 0)
        tier "unavailable"-> scope "unavailable" (report_count is 0,
                             confidence is 0)

    ``tier_used`` is preserved as the exact estimator tier; ``scope`` is
    its canonical geographic name (``local`` == ``neighborhood``). City
    tiers blended with the verified seed (``city_w * median + (1-city_w) *
    seed``) still report ``source="reports"`` because real reports
    supported the number -- only the pure no-report fallback is
    ``source="seed"``.

    Market identity uses the single canonical ``market_key(country,
    currency)`` helper (see ``market_key()`` below); 500 PKR and 500 INR
    are never the same market and no conversion is ever performed.
    """

    # Where the number came from: real eligible reports, the verified
    # per-market seed, or explicitly no data.
    source: Literal["reports", "seed", "unavailable"] = Field(
        description="reports | seed | unavailable"
    )
    # Geographic scope that actually produced the estimate.
    scope: Literal[
        "neighborhood", "neighborhood+city", "city", "country", "seed", "unavailable"
    ] = Field(description="neighborhood | neighborhood+city | city | country | seed | unavailable")
    # Eligible (accepted + fresh + same material/market/scope) reports that
    # supported the SELECTED tier. Distinct reports only (nested pools are
    # not double-counted). Always 0 for seed/unavailable.
    report_count: int = Field(ge=0, description="Eligible reports for the selected scope")
    # Canonical requested market (same normalization as market_key).
    # ``currency`` is upper-cased (or "unknown" for legacy flows);
    # ``country`` is the stripped place part or None when unnamed.
    currency: str = UNKNOWN_CURRENCY
    country: Optional[str] = None
    # Freshness window (days) applied to select the eligible population.
    # Mirrors settings.REPORT_FRESHNESS_DAYS unless the caller overrides it.
    freshness_days: int = Field(ge=0)
    # Verified seed provenance for seed estimates only
    # (settings.SEED_SOURCE); None for reports/unavailable.
    seed_source: Optional[str] = None

    def market_key(self) -> tuple[str, str]:
        """Canonical market identity for this evidence.

        Delegates to the single ``market_key(country, currency)`` helper so
        evidence can never invent a second market representation.
        """
        from app.schemas.market import market_key as _market_key

        return _market_key(self.country, self.currency)


class PriceEstimate(BaseModel):
    material_type: MaterialType
    location: str
    estimated_price_per_kg: float
    # Currency the estimate is denominated in. "unknown" for legacy flows
    # that never named one; always the requested market's currency -- the
    # estimator never converts between currencies.
    currency: str = UNKNOWN_CURRENCY
    min_price_per_kg: Optional[float] = None
    max_price_per_kg: Optional[float] = None
    used_external_context: bool = False
    external_context: Optional[str] = None
    external_sources: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    tier_used: str  # "local" (neighborhood) | "local+city" | "city" | "country" | "seed" | "unavailable"
    # Sample counts reflect the USABLE (accepted + fresh) market pools only.
    # Pools are nested: neighborhood_reports ⊆ city_reports ⊆ market_reports,
    # so city_report_count >= local_report_count and
    # country_report_count >= city_report_count. PENDING/REJECTED/stale and
    # foreign-market reports are excluded here -- these counts always agree
    # with ``evidence.report_count`` for the selected tier (see PriceEvidence).
    local_report_count: int
    city_report_count: int
    # Reports pooled at the country/market scope (same material, currency,
    # and country). Defaults to 0 so older stored payloads still parse.
    country_report_count: int = 0
    # Step 9 explainability: which eligible population actually produced the
    # number. Additive and optional so older stored payloads and older
    # clients keep parsing (missing -> None). New estimates always set it.
    evidence: Optional[PriceEvidence] = Field(default=None)
    # Photo-only pile size from the vision grader. Optional so older
    # payloads still parse. Never treated as a recorded sale quantity.
    estimated_volume_liters: Optional[float] = None
    estimated_quantity_kg: Optional[float] = None
    volume_source: Optional[str] = None


class PriceEstimateRequest(BaseModel):
    material: str
    location: str


class PriceEstimateResponse(PriceEstimate):
    pass
