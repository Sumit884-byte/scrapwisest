"""Repository package with lazy exports.

The lightweight JSON/SQLite report repository is the single live store
used by the MVP estimator. Cleanup: removed unused SQLAlchemy
``BaseRepository`` and ``PriceRepository`` (no runtime/test/CI imports).
"""

from __future__ import annotations

__all__ = ["ReportRepository", "report_repo"]


def __getattr__(name: str):
    if name in {"ReportRepository", "report_repo"}:
        from app.repositories.report_repository import ReportRepository, report_repo

        return {"ReportRepository": ReportRepository, "report_repo": report_repo}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
