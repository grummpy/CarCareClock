"""Dashboard, mileage log, service history, and the calendar download."""

from datetime import date
from pathlib import Path

from carcareclock.rules import load_defaults, load_rules
from carcareclock.web import create_app

ROOT = Path(__file__).resolve().parents[1]


def _client(tmp_path: Path):
    app = create_app(
        tmp_path / "carcareclock.sqlite",
        load_rules(ROOT / "rules" / "maryland.yaml"),
        load_defaults(ROOT / "rules" / "maintenance_defaults.yaml"),
    )
    app.config["TESTING"] = True
    return app.test_client()


def test_log_mileage_and_service_show_up(tmp_path: Path):
    client = _client(tmp_path)
    page = client.get("/")
    assert page.status_code == 200
    assert b"Due within 7 days" in page.data
    assert b"24578" in page.data or b"24,578" in page.data

    today = date.today().isoformat()
    logged = client.post(
        "/mileage",
        data={"vehicle_id": "1", "reading_date": today, "miles": "24610"},
        follow_redirects=True,
    )
    assert b"24,610" in logged.data

    service = client.post(
        "/vehicle/1/service",
        data={
            "service_date": today,
            "item_key": "oil_change",
            "mileage": "24620",
            "cost": "89.50",
            "shop": "Riverside Demo Garage",
            "notes": "Synthetic, fictional receipt.",
        },
        follow_redirects=True,
    )
    assert service.status_code == 200
    assert b"Riverside Demo Garage" in service.data
    history = client.get("/history")
    assert b"Synthetic, fictional receipt." in history.data
    assert b"89.50" in history.data

    calendar = client.get("/export.ics")
    assert calendar.status_code == 200
    assert calendar.mimetype.startswith("text/calendar")
    text = calendar.data.decode()
    assert "BEGIN:VCALENDAR" in text
    assert "America/New_York" in text
    assert "-P7D" in text


def test_interval_edit_is_per_vehicle(tmp_path: Path):
    client = _client(tmp_path)
    saved = client.post(
        "/vehicle/1/intervals",
        data={
            "item_key": "oil_change",
            "miles_oil_change": "3000",
            "months_oil_change": "4",
        },
        follow_redirects=True,
    )
    assert b"3000" in saved.data
    other = client.get("/vehicle/2")
    assert b'name="miles_oil_change"' in other.data
    # The second vehicle still has the generic placeholder, not the edited 3000.
    assert b"value=\"3000\"" not in other.data
