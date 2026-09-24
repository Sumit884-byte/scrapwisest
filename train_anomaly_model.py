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

# Compute per-(material, market) medians (Step 4: never learn a mixed-market
# distribution). Legacy rows without country/currency fall back to a
# material-only median so old synthetic data still trains.
from collections import defaultdict

from app.schemas.market import market_key

prices_by_market: dict[tuple, list[float]] = defaultdict(list)
for r in raw:
    price = r.get("price_per_kg", r.get("price_paid_pkr_per_kg"))
    key = (r["material_type"], market_key(r.get("country"), r.get("currency")))
    prices_by_market[key].append(price)

medians = {m: statistics.median(p) for m, p in prices_by_market.items()}

reports = [
    {
        "price_per_kg": r.get("price_per_kg", r.get("price_paid_pkr_per_kg")),
        "quantity_kg": r["quantity_kg"],
        "material_median": medians[
            (r["material_type"], market_key(r.get("country"), r.get("currency")))
        ],
    }
    for r in raw
]

model = train_ml_model(reports)
if model:
    print(f"Trained on {len(reports)} reports. Model saved to models/isolation_forest.pkl")
else:
    print("Not enough data to train.")
