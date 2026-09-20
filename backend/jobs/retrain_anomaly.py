"""
Retrain the Isolation Forest from trusted reports already in SQLite.

Meant to run as a Nebius Serverless Job (or locally) after enough sales
have been logged. Does not call an LLM.

    python -m jobs.retrain_anomaly
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.anomaly_detector import retrain

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")


def main() -> int:
    trained = retrain()
    if trained:
        print("Retrained Isolation Forest from trusted reports.")
        return 0
    print("Not enough trusted reports to retrain yet.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
