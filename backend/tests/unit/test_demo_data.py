from __future__ import annotations

from pathlib import Path

from app.schemas.report import MaterialType
from app.services.price_estimator import PriceEstimatorService
from app.repositories.report_repository import ReportRepository


def test_demo_fixture_has_local_and_city_depth(tmp_path: Path):
    repo = ReportRepository(tmp_path / "reports.db")
    from scripts.load_demo_data import DATA_PATH, load_demo_reports

    # The loader uses the configured singleton repository, so validate the
    # fixture independently through its documented JSON contract here.
    import json

    records = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    pet = [r for r in records if r["material_type"] == MaterialType.PLASTIC_PET.value]
    local = [r for r in pet if r["location"].lower() == "income colony"]

    assert len(local) >= 5
    assert len(pet) >= 10
