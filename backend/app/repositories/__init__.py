"""Repository package with lazy exports.

The lightweight JSON/SQLite report repository is used by the MVP estimator.
Avoid importing the SQLAlchemy repository base just because a maintenance
script needs to load reports.
"""

from __future__ import annotations

__all__ = ["BaseRepository", "ReportRepository", "report_repo", "PriceRepository", "price_repo"]


def __getattr__(name: str):
    if name == "BaseRepository":
        from app.repositories.base import BaseRepository

        return BaseRepository
    if name in {"ReportRepository", "report_repo"}:
        from app.repositories.report_repository import ReportRepository, report_repo

        return {"ReportRepository": ReportRepository, "report_repo": report_repo}[name]
    if name in {"PriceRepository", "price_repo"}:
        from app.repositories.price_repository import PriceRepository, price_repo

        return {"PriceRepository": PriceRepository, "price_repo": price_repo}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
