"""
Report repository for reading and storing PriceReports.
Preserves full backwards compatibility with SQLite-backed reports.db.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

from app.core.config import settings
from app.schemas.report import MaterialType, PriceReport

logger = logging.getLogger(__name__)


class ReportRepository:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (settings.BACKEND_DIR / "reports.db")

    def _conn(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db_path, check_same_thread=False)
        con.execute("CREATE TABLE IF NOT EXISTS reports (data TEXT NOT NULL)")
        con.execute(
            "CREATE TABLE IF NOT EXISTS pending_reports "
            "(picker_id TEXT PRIMARY KEY, data TEXT NOT NULL)"
        )
        con.commit()
        return con

    def add(self, report: PriceReport) -> None:
        """Store a validated, non-anomalous price report."""
        with self._conn() as con:
            con.execute("INSERT INTO reports VALUES (?)", (report.model_dump_json(),))
        logger.info(
            "Saved report to store: material=%s quantity=%.2fkg price_per_kg=%.2f location=%s",
            report.material_type.value if hasattr(report.material_type, "value") else str(report.material_type),
            report.quantity_kg,
            report.price_paid_pkr_per_kg,
            report.location,
        )

    def all_reports(self) -> List[PriceReport]:
        """Fetch all reports from the store."""
        con = self._conn()
        rows = con.execute("SELECT data FROM reports").fetchall()
        reports = [PriceReport.model_validate_json(r[0]) for r in rows]
        logger.debug("Fetched %d reports from store (%s)", len(reports), self.db_path)
        return reports

    def trusted_reports(self) -> List[PriceReport]:
        """Fetch reports that do not require picker confirmation."""
        return [r for r in self.all_reports() if not r.needs_confirmation]

    def save_pending(self, report: PriceReport) -> None:
        """Save or replace the one pending review for a picker."""
        if not report.picker_id:
            raise ValueError("A picker_id is required for pending reports")
        with self._conn() as con:
            con.execute(
                "INSERT INTO pending_reports (picker_id, data) VALUES (?, ?) "
                "ON CONFLICT(picker_id) DO UPDATE SET data=excluded.data",
                (report.picker_id, report.model_dump_json()),
            )

    def get_pending(self, picker_id: str) -> Optional[PriceReport]:
        """Return the current pending review for a picker, if any."""
        with self._conn() as con:
            row = con.execute(
                "SELECT data FROM pending_reports WHERE picker_id = ?",
                (picker_id,),
            ).fetchone()
        return PriceReport.model_validate_json(row[0]) if row else None

    def clear_pending(self, picker_id: str) -> None:
        """Remove a pending report after acceptance."""
        with self._conn() as con:
            con.execute("DELETE FROM pending_reports WHERE picker_id = ?", (picker_id,))

    def find_by_material_and_location(
        self,
        material: MaterialType | str,
        location: Optional[str] = None,
        trusted_only: bool = True,
    ) -> List[PriceReport]:
        """Find reports filtered by material and optional location."""
        reports = self.trusted_reports() if trusted_only else self.all_reports()
        mat_val = material.value if isinstance(material, MaterialType) else str(material).lower()

        filtered = [
            r for r in reports
            if (r.material_type.value if hasattr(r.material_type, "value") else str(r.material_type).lower()) == mat_val
        ]
        if location:
            loc_lower = location.strip().lower()
            filtered = [r for r in filtered if r.location.strip().lower() == loc_lower]

        return filtered


# Singleton instance for repository
report_repo = ReportRepository()
