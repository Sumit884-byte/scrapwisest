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
from app.services.location_resolver import UNKNOWN_CURRENCY, normalize_place_part

DATA_PATH = _REPO_ROOT / "demo_data" / "reports.json"
DEMO_PICKER_ID = "demo-seed"


def _demo_keys(report: PriceReport) -> tuple[tuple, tuple]:
    """Full market-aware key plus a legacy key.

    The legacy key (no currency/country/city) keeps the loader idempotent
    for databases seeded before the global market model existed.
    """
    material = (
        report.material_type.value
        if hasattr(report.material_type, "value")
        else str(report.material_type)
    )
    legacy = (
        material,
        report.quantity_kg,
        report.price_per_kg,
        report.location.strip().lower(),
    )
    full = legacy + (
        (report.currency or UNKNOWN_CURRENCY).strip().upper(),
        (report.country or "").strip().lower(),
        (report.city or "").strip().lower(),
    )
    return full, legacy


def load_demo_reports(*, replace: bool = False) -> tuple[int, int]:
    """Insert demo reports and return ``(inserted, skipped)`` counts."""
    records = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    existing = report_repo.all_reports()

    if replace:
        # The repository intentionally has no destructive delete operation.
        # Keep replacement out of the normal loader to avoid accidental data loss.
        raise ValueError("--replace is not supported; use a fresh demo database instead")

    existing_demo: set[tuple] = set()
    for report in existing:
        if report.picker_id != DEMO_PICKER_ID:
            continue
        full, legacy = _demo_keys(report)
        existing_demo.add(full)
        existing_demo.add(legacy)

    inserted = 0
    skipped = 0
    for record in records:
        material = MaterialType(record["material_type"])
        quantity = float(record["quantity_kg"])
        # New files use "price_per_kg"; pre-migration files used the legacy key.
        if "price_per_kg" in record:
            price_per_kg = float(record["price_per_kg"])
        else:
            price_per_kg = float(record["price_paid_pkr_per_kg"])
        location = str(record["location"]).strip()
        currency = str(record.get("currency", UNKNOWN_CURRENCY)).strip() or UNKNOWN_CURRENCY
        country = normalize_place_part(record.get("country"))
        city = normalize_place_part(record.get("city"))

        candidate = PriceReport(
            material_type=material,
            quantity_kg=quantity,
            total_price=round(quantity * price_per_kg, 2),
            price_per_kg=price_per_kg,
            currency=currency,
            country=country,
            city=city,
            neighborhood=location,
            location=location,
            timestamp=datetime.now(timezone.utc),
            picker_id=DEMO_PICKER_ID,
        )
        full, legacy = _demo_keys(candidate)

        if full in existing_demo or legacy in existing_demo:
            skipped += 1
            continue

        report_repo.add(candidate)
        existing_demo.add(full)
        existing_demo.add(legacy)
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
