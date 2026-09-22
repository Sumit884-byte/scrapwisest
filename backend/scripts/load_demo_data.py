"""Load the repeatable Scrapwisest demo market dataset.

Usage from the repository root:

    python backend/scripts/load_demo_data.py

The loader is idempotent. It identifies its own rows using the ``demo-seed``
picker id and will not insert them twice. It writes to the same legacy SQLite
repository used by the current price estimator and report API.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.repositories.report_repository import report_repo
from app.schemas.report import MaterialType, PriceReport

DATA_PATH = _REPO_ROOT / "demo_data" / "reports.json"
DEMO_PICKER_ID = "demo-seed"


def load_demo_reports(*, replace: bool = False) -> tuple[int, int]:
    """Insert demo reports and return ``(inserted, skipped)`` counts."""
    records = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    existing = report_repo.all_reports()

    if replace:
        # The repository intentionally has no destructive delete operation.
        # Keep replacement out of the normal loader to avoid accidental data loss.
        raise ValueError("--replace is not supported; use a fresh demo database instead")

    existing_demo = {
        (
            report.material_type.value,
            report.quantity_kg,
            report.price_paid_pkr_per_kg,
            report.location.strip().lower(),
        )
        for report in existing
        if report.picker_id == DEMO_PICKER_ID
    }

    inserted = 0
    skipped = 0
    for record in records:
        material = MaterialType(record["material_type"])
        quantity = float(record["quantity_kg"])
        price_per_kg = float(record["price_paid_pkr_per_kg"])
        location = str(record["location"]).strip()
        key = (material.value, quantity, price_per_kg, location.lower())

        if key in existing_demo:
            skipped += 1
            continue

        report_repo.add(
            PriceReport(
                material_type=material,
                quantity_kg=quantity,
                price_paid_pkr=round(quantity * price_per_kg, 2),
                price_paid_pkr_per_kg=price_per_kg,
                location=location,
                timestamp=datetime.now(timezone.utc),
                picker_id=DEMO_PICKER_ID,
            )
        )
        inserted += 1

    return inserted, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    inserted, skipped = load_demo_reports()
    print(f"Demo dataset loaded: {inserted} inserted, {skipped} already present.")
    print(f"Database: {report_repo.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
