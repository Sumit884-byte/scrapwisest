"""
Train the Isolation Forest on synthethic_report.json.
Run once: python train_anomaly_model.py
"""

import json
import statistics
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.anomaly_detector import train_ml_model

raw = json.loads(Path("synthethic_report.json").read_text(encoding="utf-8"))

# Compute per-material median across all reports (used as normalization baseline)
from collections import defaultdict
prices_by_material: dict[str, list[float]] = defaultdict(list)
for r in raw:
    prices_by_material[r["material_type"]].append(r["price_paid_pkr_per_kg"])

medians = {m: statistics.median(p) for m, p in prices_by_material.items()}

reports = [
    {
        "price_paid_pkr_per_kg": r["price_paid_pkr_per_kg"],
        "quantity_kg": r["quantity_kg"],
        "material_median": medians[r["material_type"]],
    }
    for r in raw
]

model = train_ml_model(reports)
if model:
    print(f"Trained on {len(reports)} reports. Model saved to models/isolation_forest.pkl")
else:
    print("Not enough data to train.")
