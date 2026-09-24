"""
Canonical report trust lifecycle for Scrapwisest (Step 8).

Single authority for "which reports are market data":

    ACCEPTED -> eligible for price estimation + anomaly history
    PENDING  -> stored for review, NEVER market data
    REJECTED -> stored for audit, NEVER market data

Trust composes with Step 7 freshness and Steps 1-6 market/location scoping:

    all reports -> accepted only -> fresh only -> market/location filtering

This module has no repository imports (import-cycle safety): repository and
service layers import these helpers, never the reverse.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Iterable, List, Optional, TypeVar

from app.schemas.report import PriceReport, ReportTrustStatus

T = TypeVar("T")

TRUSTED_STATUS_VALUE = ReportTrustStatus.ACCEPTED.value
PENDING_STATUS_VALUE = ReportTrustStatus.PENDING.value
REJECTED_STATUS_VALUE = ReportTrustStatus.REJECTED.value


class InvalidTrustTransitionError(ValueError):
    """Raised when a review transition violates the trust state machine."""


def _status_value(report) -> str:
    raw = getattr(report, "trust_status", ReportTrustStatus.ACCEPTED.value)
    if isinstance(raw, Enum):
        return str(raw.value).strip().lower()
    return str(raw or "").strip().lower()


def trust_status_of(report) -> str:
    """Canonical trust value for ``report`` (plain lowercase string)."""
    return _status_value(report)


def is_trusted_report(report) -> bool:
    """True only for explicitly ACCEPTED reports.

    Defensive: both the canonical ``trust_status`` and the legacy
    ``needs_confirmation`` flag must agree. A report with
    ``trust_status=ACCEPTED`` but ``needs_confirmation=True`` is NOT trusted
    (the PriceReport validator normally prevents this state, but callers
    must never trust contradictory data).
    """
    if bool(getattr(report, "needs_confirmation", False)):
        return False
    return _status_value(report) == TRUSTED_STATUS_VALUE


def is_pending_report(report) -> bool:
    return _status_value(report) == PENDING_STATUS_VALUE


def is_rejected_report(report) -> bool:
    return _status_value(report) == REJECTED_STATUS_VALUE


def filter_trusted_reports(reports: Iterable[T]) -> List[T]:
    """Return only ACCEPTED reports (order preserved)."""
    return [r for r in reports if is_trusted_report(r)]


def get_trusted_reports(reports: Iterable[T]) -> List[T]:
    """Canonical trusted-report query (alias for ``filter_trusted_reports``)."""
    return filter_trusted_reports(reports)


def filter_trusted_fresh_reports(
    reports: Iterable[T],
    now: Optional[datetime] = None,
    freshness_days: Optional[int] = None,
) -> List[T]:
    """Accepted AND fresh reports (Step 8 + Step 7 composition).

    Trust is applied first so pending/rejected data never reaches the
    freshness filter as market data; the final population satisfies both
    constraints regardless of order.
    """
    # Local import keeps this module free of service-layer cycles.
    from app.services.report_freshness import filter_fresh_reports

    trusted = filter_trusted_reports(reports)
    return filter_fresh_reports(trusted, now=now, freshness_days=freshness_days)


def decide_trust_status(
    has_validation_reasons: bool = False,
    is_anomalous: bool = False,
) -> ReportTrustStatus:
    """Map pipeline outcome to its canonical trust state.

    Normal (no validation reasons, not anomalous) -> ACCEPTED.
    Anything flagged (validation OR anomaly) -> PENDING.
    REJECTED is only ever assigned by explicit human/service review,
    never automatically here.
    """
    if has_validation_reasons or is_anomalous:
        return ReportTrustStatus.PENDING
    return ReportTrustStatus.ACCEPTED


def mark_pending(report: PriceReport, reason: Optional[str] = None) -> PriceReport:
    """Return a copy of ``report`` marked PENDING (flagged -> pending)."""
    update: dict = {"trust_status": ReportTrustStatus.PENDING.value, "needs_confirmation": True}
    if reason is not None:
        update["confirmation_reason"] = reason
    elif getattr(report, "confirmation_reason", None) is None:
        update["confirmation_reason"] = "flagged for review"
    return report.model_copy(update=update)


def mark_accepted(report: PriceReport) -> PriceReport:
    """Return a copy of ``report`` marked ACCEPTED (normal -> accepted)."""
    return report.model_copy(
        update={
            "trust_status": ReportTrustStatus.ACCEPTED.value,
            "needs_confirmation": False,
            "confirmation_reason": None,
        }
    )


def accept_pending_report(report: PriceReport) -> PriceReport:
    """Transition PENDING -> ACCEPTED (review approval).

    Raises InvalidTrustTransitionError for any other starting state.
    """
    if _status_value(report) != PENDING_STATUS_VALUE:
        raise InvalidTrustTransitionError(
            f"cannot accept report with trust_status={_status_value(report)!r}; only 'pending' can be accepted"
        )
    return mark_accepted(report)


def reject_pending_report(
    report: PriceReport, reason: Optional[str] = None
) -> PriceReport:
    """Transition PENDING -> REJECTED (review rejection, kept for audit).

    Raises InvalidTrustTransitionError for any other starting state.
    """
    if _status_value(report) != PENDING_STATUS_VALUE:
        raise InvalidTrustTransitionError(
            f"cannot reject report with trust_status={_status_value(report)!r}; only 'pending' can be rejected"
        )
    return report.model_copy(
        update={
            "trust_status": ReportTrustStatus.REJECTED.value,
            "needs_confirmation": False,
            "confirmation_reason": reason or getattr(report, "confirmation_reason", None) or "rejected on review",
        }
    )


def review_report(report: PriceReport, decision: str, reason: Optional[str] = None) -> PriceReport:
    """Apply a review decision ('accept' | 'reject') to a PENDING report."""
    normalized = (decision or "").strip().lower()
    if normalized in {"accept", "accepted", "approve", "approved"}:
        return accept_pending_report(report)
    if normalized in {"reject", "rejected", "decline", "declined"}:
        return reject_pending_report(report, reason=reason)
    raise InvalidTrustTransitionError(
        f"unknown review decision {decision!r}; expected 'accept' or 'reject'"
    )
