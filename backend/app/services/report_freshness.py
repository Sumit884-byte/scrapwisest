"""
Report freshness helper for Scrapwisest (Step 7).

Recency-aware market data: only *fresh* reports contribute to a current
market estimate or anomaly comparison population. Stale reports are never
deleted, but they no longer influence current medians.

Definition of "fresh" (deliberately simple, no decay/reputation/ML)::

    fresh  <=>  report_timestamp >= now - timedelta(days=freshness_days)

Rules:
- Inclusive boundary: a report exactly ``freshness_days`` old is fresh.
- Timezone-safe: naive datetimes are assumed to be UTC (never local time).
- Future timestamps are fresh (a slightly-future clock must not turn a
  current report into an ancient one).
- Missing/unparseable timestamps are NEVER fresh (unknown age must not
  masquerade as current data).

Both the price estimator and the anomaly detector must use these helpers
so the freshness rule has exactly one implementation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, TypeVar

from app.core.config import settings

T = TypeVar("T")


def utc_now() -> datetime:
    """Current timezone-aware UTC time (single clock for freshness)."""
    return datetime.now(timezone.utc)


def _as_aware_utc(value: datetime | str | None) -> Optional[datetime]:
    """Normalize a timestamp to aware UTC, or None when unknown.

    - ``None`` -> None (missing timestamp is never fresh).
    - ``datetime`` naive -> assumed UTC (never local time).
    - ISO string -> parsed; naive results assumed UTC; unparseable -> None.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Pydantic/SQLite emit trailing "Z"; datetime.fromisoformat needs "+00:00".
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        value = parsed
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_now(now: datetime | None) -> datetime:
    parsed = _as_aware_utc(now) if now is not None else None
    return parsed if parsed is not None else utc_now()


def _resolve_window(freshness_days: int | None) -> int:
    if freshness_days is None:
        return int(settings.REPORT_FRESHNESS_DAYS)
    return int(freshness_days)


def is_report_fresh(
    report,
    now: datetime | None = None,
    freshness_days: int | None = None,
) -> bool:
    """True when ``report`` counts as fresh for current-market purposes.

    ``report`` may be a ``PriceReport`` (or anything with a ``timestamp``
    attribute), a raw ``datetime``, or an ISO string. Deterministic when
    ``now`` is injected; defaults to the current UTC time and the
    configured ``REPORT_FRESHNESS_DAYS`` window.
    """
    days = _resolve_window(freshness_days)
    current = _resolve_now(now)
    if isinstance(report, (datetime, str)) or report is None:
        ts_raw = report
    else:
        ts_raw = getattr(report, "timestamp", None)
    ts = _as_aware_utc(ts_raw)
    if ts is None:
        return False
    cutoff = current - timedelta(days=days)
    # Inclusive: exactly at the boundary is fresh. Future timestamps are
    # fresh by the same comparison (ts >= cutoff).
    return ts >= cutoff


def filter_fresh_reports(
    reports: Iterable[T],
    now: datetime | None = None,
    freshness_days: int | None = None,
) -> List[T]:
    """Return only the fresh subset of ``reports`` (order preserved)."""
    return [r for r in reports if is_report_fresh(r, now=now, freshness_days=freshness_days)]
