"""
SQLite-backed report store.
Serializes each PriceReport as JSON — avoids schema migrations as the model evolves.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.backend.agent_schemas.report import PriceReport

_DB_PATH = Path("reports.db")


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS reports (data TEXT NOT NULL)")
    con.commit()
    return con


def add(report: PriceReport) -> None:
    with _conn() as con:
        con.execute("INSERT INTO reports VALUES (?)", (report.model_dump_json(),))


def all_reports() -> list[PriceReport]:
    con = _conn()
    rows = con.execute("SELECT data FROM reports").fetchall()
    return [PriceReport.model_validate_json(r[0]) for r in rows]
