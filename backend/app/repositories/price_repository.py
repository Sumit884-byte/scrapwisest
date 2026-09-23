"""
Price repository for fetching historical pricing benchmarks and statistics.
"""

from __future__ import annotations

import logging
import statistics
from typing import Dict, List, Optional

from app.repositories.report_repository import ReportRepository, report_repo
from app.schemas.report import MaterialType, PriceReport

logger = logging.getLogger(__name__)


class PriceRepository:
    def __init__(self, repo: Optional[ReportRepository] = None):
        self.repo = repo or report_repo

    def get_prices_for(self, material: MaterialType | str, location: Optional[str] = None) -> List[float]:
        """Return list of prices paid per kg for a given material and optional location."""
        reports = self.repo.find_by_material_and_location(material, location, trusted_only=True)
        return [r.price_per_kg for r in reports]

    def get_material_medians(self) -> Dict[str, float]:
        """Compute recent price median per material across all trusted reports."""
        trusted = self.repo.trusted_reports()
        prices_by_mat: Dict[str, List[float]] = {}
        for r in trusted:
            mat_key = r.material_type.value if hasattr(r.material_type, "value") else str(r.material_type)
            prices_by_mat.setdefault(mat_key, []).append(r.price_per_kg)

        return {
            mat: statistics.median(prices)
            for mat, prices in prices_by_mat.items()
            if prices
        }


price_repo = PriceRepository()
