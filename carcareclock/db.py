"""SQLite storage. The database lives in the gitignored data folder.

VINs and license plates are not columns. Do not add them.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY,
    nickname TEXT NOT NULL,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    model_year INTEGER NOT NULL,
    fuel TEXT NOT NULL,
    vehicle_type TEXT NOT NULL DEFAULT 'passenger',
    gvwr INTEGER,
    ownership TEXT NOT NULL,
    title_date TEXT,
    county TEXT NOT NULL,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intervals (
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    miles INTEGER,
    months INTEGER,
    PRIMARY KEY (vehicle_id, item_key)
);

CREATE TABLE IF NOT EXISTS odometer (
    id INTEGER PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    reading_date TEXT NOT NULL,
    miles INTEGER NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    item_key TEXT,
    service_date TEXT NOT NULL,
    mileage INTEGER,
    cost_cents INTEGER,
    shop TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS compliance (
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    last_completed TEXT,
    next_due TEXT,
    period_years INTEGER,
    PRIMARY KEY (vehicle_id, kind)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('reminder_window_days', '7')"
    )
    conn.commit()


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def iso(day: date | None) -> str | None:
    return None if day is None else day.isoformat()


def parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)
