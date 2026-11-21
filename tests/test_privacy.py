"""No VIN or plate column, demo data is fictional, and the data folder is gitignored."""

from pathlib import Path

from carcareclock.db import connect, init_db, table_columns
from carcareclock.rules import load_defaults
from carcareclock.service import seed_demo

ROOT = Path(__file__).resolve().parents[1]


def test_schema_and_seed_have_no_vin_or_plate(tmp_path: Path):
    conn = connect(tmp_path / "carcareclock.sqlite")
    init_db(conn)
    for table in ("vehicles", "odometer", "services", "compliance", "intervals", "settings"):
        columns = table_columns(conn, table)
        assert "vin" not in columns
        assert "plate" not in columns
        assert "license_plate" not in columns
        assert "email" not in columns
    seed_demo(conn, load_defaults(ROOT / "rules" / "maintenance_defaults.yaml"))
    nicknames = [row["nickname"] for row in conn.execute("SELECT nickname FROM vehicles")]
    assert "Demo Kia" in nicknames
    assert all(row["is_demo"] == 1 for row in conn.execute("SELECT is_demo FROM vehicles"))
    blob = " ".join(
        " ".join(str(value) for value in row) for row in conn.execute("SELECT * FROM services")
    )
    assert "Riverside Demo Garage" in blob
    assert "@" not in blob


def test_data_folder_is_gitignored():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/" in text
    defaults = (ROOT / "rules" / "maintenance_defaults.yaml").read_text(encoding="utf-8")
    assert "GENERIC PLACEHOLDER" in defaults


def test_existing_local_database_gains_interval_provenance_columns(tmp_path: Path):
    path = tmp_path / "legacy.sqlite"
    legacy = connect(path)
    legacy.execute(
        """
        CREATE TABLE intervals (
            vehicle_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            miles INTEGER,
            months INTEGER,
            PRIMARY KEY (vehicle_id, item_key)
        )
        """
    )
    legacy.execute("INSERT INTO intervals (vehicle_id, item_key, miles, months) VALUES (1, 'oil_change', 5000, 6)")
    legacy.commit()
    init_db(legacy)
    assert {"source_reference", "service_profile", "guidance_checked_on"} <= table_columns(legacy, "intervals")
    row = legacy.execute("SELECT * FROM intervals WHERE vehicle_id = 1").fetchone()
    assert row["source_reference"] == ""
    assert row["service_profile"] == "unverified"
    assert row["guidance_checked_on"] == ""
    legacy.close()
