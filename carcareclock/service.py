"""Turn the database and the YAML rules into dashboard rows and calendar items."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from carcareclock.db import iso, parse_iso
from carcareclock.ics_export import CalendarItem
from carcareclock.rules import MaintenanceDefaults, MarylandRules
from carcareclock.schedule import (
    add_months,
    assess_registration,
    assess_veip,
    due_phrase,
    format_long_date,
    in_reminder_window,
    miles_per_day,
    reminder_status,
    whichever_comes_first,
)

CHIP_KEYS = ("veip", "registration", "oil_change", "engine_air_filter")
TIMELINE_HORIZON_DAYS = 180


@dataclass
class ItemView:
    vehicle_id: int
    vehicle_name: str
    key: str
    label: str
    due: date | None
    status: str
    phrase: str
    date_label: str
    detail: str
    tone: str

    def to_calendar(self, verify: str) -> CalendarItem | None:
        if self.due is None:
            return None
        extra = ""
        if self.key in {"veip", "registration"}:
            extra = " " + verify
        return CalendarItem(
            uid=f"carcareclock-{self.vehicle_id}-{self.key}-{self.due.isoformat()}@local",
            summary=f"{self.label} — {self.vehicle_name}",
            description=(self.detail + extra).strip(),
            due=self.due,
        )


def reminder_window_days(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM settings WHERE key = 'reminder_window_days'").fetchone()
    if row is None:
        return 7
    return int(row["value"])


def set_reminder_window_days(conn: sqlite3.Connection, days: int) -> None:
    if days < 0 or days > 365:
        raise ValueError("Reminder window must be from 0 to 365 days.")
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES ('reminder_window_days', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(days),),
    )
    conn.commit()


def _vehicle_dict(row: sqlite3.Row, compliance: dict[str, sqlite3.Row]) -> dict[str, Any]:
    veip = compliance.get("veip")
    return {
        "county": row["county"],
        "fuel": row["fuel"],
        "vehicle_type": row["vehicle_type"],
        "model_year": row["model_year"],
        "gvwr": row["gvwr"],
        "ownership": row["ownership"],
        "title_date": parse_iso(row["title_date"]),
        "last_completed": parse_iso(veip["last_completed"]) if veip else None,
        "next_due": parse_iso(veip["next_due"]) if veip else None,
    }


def _readings(conn: sqlite3.Connection, vehicle_id: int) -> list[tuple[date, int]]:
    rows = conn.execute(
        "SELECT reading_date, miles FROM odometer WHERE vehicle_id = ? ORDER BY reading_date, id",
        (vehicle_id,),
    ).fetchall()
    return [(parse_iso(row["reading_date"]), int(row["miles"])) for row in rows]


def _latest_service(conn: sqlite3.Connection, vehicle_id: int, item_key: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT service_date, mileage FROM services
        WHERE vehicle_id = ? AND item_key = ?
        ORDER BY service_date DESC, id DESC
        LIMIT 1
        """,
        (vehicle_id, item_key),
    ).fetchone()


def _tone(key: str, status: str) -> str:
    if status == "overdue":
        return "overdue"
    if status == "exempt":
        return "exempt"
    return {
        "veip": "emissions",
        "registration": "registration",
        "oil_change": "oil",
        "engine_air_filter": "filter",
        "cabin_air_filter": "filter",
        "tire_rotation": "tire",
        "brake_inspection": "brake",
        "wipers": "wiper",
        "battery": "battery",
        "coolant": "coolant",
    }.get(key, "plain")


def items_for_vehicle(
    conn: sqlite3.Connection,
    vehicle: sqlite3.Row,
    rules: MarylandRules,
    defaults: MaintenanceDefaults,
    today: date,
    window_days: int,
) -> list[ItemView]:
    compliance = {
        row["kind"]: row
        for row in conn.execute(
            "SELECT * FROM compliance WHERE vehicle_id = ?", (vehicle["id"],)
        ).fetchall()
    }
    readings = _readings(conn, vehicle["id"])
    views: list[ItemView] = []

    veip = assess_veip(_vehicle_dict(vehicle, compliance), rules, today)
    if not veip.required:
        status = "not_required"
        phrase = "Not required"
    elif (
        veip.exempt
        and veip.due_source != "notice"
        and not in_reminder_window(veip.due, today, window_days)
    ):
        status = "exempt"
        phrase = "Exempt for now" if veip.due else "Exempt"
    else:
        status = reminder_status(veip.due, today, window_days)
        phrase = due_phrase(veip.due, today)
    detail = veip.detail
    if veip.notice is not None:
        detail += (
            f" Email notice about {format_long_date(veip.notice.email_on)}"
            f" ({rules.email_weeks_before_due} weeks ahead)."
            f" Mail notice roughly {format_long_date(veip.notice.mail_opens)}"
            f" to {format_long_date(veip.notice.mail_closes)}."
        )
    if veip.late_fee_usd:
        detail += f" Estimated late fee so far: ${veip.late_fee_usd}."
    views.append(
        ItemView(
            vehicle_id=vehicle["id"],
            vehicle_name=vehicle["nickname"],
            key="veip",
            label="Emissions test",
            due=veip.due,
            status=status,
            phrase=phrase,
            date_label=format_long_date(veip.due) if veip.due else "",
            detail=detail,
            tone=_tone("veip", status),
        )
    )

    reg_row = compliance.get("registration")
    card = parse_iso(reg_row["next_due"]) if reg_row else None
    period = int(reg_row["period_years"]) if reg_row and reg_row["period_years"] else None
    registration = assess_registration(card, period, rules)
    status = reminder_status(registration.planning_due, today, window_days)
    detail = registration.detail
    if registration.early_renew_opens:
        detail += (
            f" Renewal opens {format_long_date(registration.early_renew_opens)}"
            f" ({rules.early_renew_days} days before the card date)."
        )
    if registration.published_notice_on:
        detail += f" Notice date from the rules file: {format_long_date(registration.published_notice_on)}."
    else:
        detail += " The rules file has no fixed renewal-notice lead time."
    if registration.month_end and registration.expiration and registration.month_end != registration.expiration:
        detail += f" Last day of that month: {format_long_date(registration.month_end)}."
    views.append(
        ItemView(
            vehicle_id=vehicle["id"],
            vehicle_name=vehicle["nickname"],
            key="registration",
            label="Registration",
            due=registration.planning_due,
            status=status,
            phrase=due_phrase(registration.planning_due, today),
            date_label=format_long_date(registration.planning_due) if registration.planning_due else "",
            detail=detail,
            tone=_tone("registration", status),
        )
    )

    stored = {
        row["item_key"]: row
        for row in conn.execute(
            "SELECT item_key, miles, months FROM intervals WHERE vehicle_id = ?",
            (vehicle["id"],),
        ).fetchall()
    }
    labels = {item.key: item.label for item in defaults.items}
    keys = list(dict.fromkeys([*labels.keys(), *stored.keys()]))
    for key in keys:
        row = stored.get(key)
        if row is None:
            continue
        last = _latest_service(conn, vehicle["id"], key)
        result = whichever_comes_first(
            last_date=parse_iso(last["service_date"]) if last else None,
            last_miles=int(last["mileage"]) if last and last["mileage"] is not None else None,
            months_interval=row["months"],
            miles_interval=row["miles"],
            readings=readings,
            today=today,
        )
        status = reminder_status(result.due, today, window_days)
        if result.due is None and result.needs_readings:
            phrase = "Needs mileage readings"
            status = "needs_readings"
        elif result.due is None:
            phrase = "Log a service to start"
            status = "needs_date"
        else:
            phrase = due_phrase(result.due, today)
        reason = {"miles": "mileage interval", "months": "months interval", "both": "mileage and months"}.get(
            result.reason or "", ""
        )
        detail = f"Whichever comes first. Next limit: {reason}." if reason else "No service logged yet."
        views.append(
            ItemView(
                vehicle_id=vehicle["id"],
                vehicle_name=vehicle["nickname"],
                key=key,
                label=labels.get(key, key.replace("_", " ").title()),
                due=result.due,
                status=status,
                phrase=phrase,
                date_label=format_long_date(result.due) if result.due else "",
                detail=detail,
                tone=_tone(key, status),
            )
        )
    return views


def all_items(
    conn: sqlite3.Connection,
    rules: MarylandRules,
    defaults: MaintenanceDefaults,
    today: date | None = None,
) -> list[ItemView]:
    today = today or date.today()
    window = reminder_window_days(conn)
    vehicles = conn.execute("SELECT * FROM vehicles ORDER BY id").fetchall()
    items: list[ItemView] = []
    for vehicle in vehicles:
        items.extend(items_for_vehicle(conn, vehicle, rules, defaults, today, window))
    return items


def reminder_lines(items: list[ItemView]) -> list[str]:
    lines = []
    for item in items:
        if item.status not in {"overdue", "due_soon"}:
            continue
        when = item.date_label or "no date"
        lines.append(f"{item.vehicle_name}: {item.label} {item.phrase.lower()} ({when}).")
    return lines


def calendar_items(items: list[ItemView], today: date, verify: str) -> list[CalendarItem]:
    start = today - timedelta(days=30)
    end = today + timedelta(days=365)
    chosen: list[CalendarItem] = []
    for item in items:
        if item.due is None or item.status in {"exempt", "not_required"}:
            continue
        if start <= item.due <= end:
            built = item.to_calendar(verify)
            if built:
                chosen.append(built)
    return chosen


def vehicle_cards(
    conn: sqlite3.Connection,
    rules: MarylandRules,
    defaults: MaintenanceDefaults,
    today: date | None = None,
) -> list[dict[str, Any]]:
    today = today or date.today()
    window = reminder_window_days(conn)
    cards = []
    for vehicle in conn.execute("SELECT * FROM vehicles ORDER BY id").fetchall():
        views = items_for_vehicle(conn, vehicle, rules, defaults, today, window)
        by_key = {item.key: item for item in views}
        readings = _readings(conn, vehicle["id"])
        latest = readings[-1][1] if readings else None
        rate = miles_per_day(readings)
        chips = [by_key[key] for key in CHIP_KEYS if key in by_key]
        cards.append(
            {
                "id": vehicle["id"],
                "nickname": vehicle["nickname"],
                "make": vehicle["make"],
                "model": vehicle["model"],
                "model_year": vehicle["model_year"],
                "county": vehicle["county"],
                "is_demo": bool(vehicle["is_demo"]),
                "fuel": vehicle["fuel"],
                "miles": latest,
                "miles_display": f"{latest:,}" if latest is not None else "—",
                "rate_display": f"about {rate:.0f} miles/day" if rate else "log two readings to estimate",
                "chips": chips,
            }
        )
    return cards


def timeline(items: list[ItemView], today: date) -> list[ItemView]:
    horizon = today + timedelta(days=TIMELINE_HORIZON_DAYS)
    chosen = [
        item
        for item in items
        if item.due is not None and item.status not in {"exempt", "not_required"} and item.due <= horizon
    ]
    chosen.sort(key=lambda item: (item.due or today, item.vehicle_name, item.label))
    return chosen


def log_mileage(
    conn: sqlite3.Connection,
    vehicle_id: int,
    reading_date: date,
    miles: int,
    notes: str = "",
) -> None:
    if miles < 0 or miles > 9_999_999:
        raise ValueError("Enter a mileage from 0 to 9,999,999.")
    previous = conn.execute(
        """
        SELECT miles FROM odometer
        WHERE vehicle_id = ? AND reading_date <= ?
        ORDER BY reading_date DESC, id DESC LIMIT 1
        """,
        (vehicle_id, iso(reading_date)),
    ).fetchone()
    if previous and miles < int(previous["miles"]):
        raise ValueError("That reading is lower than an earlier reading on or before that date.")
    following = conn.execute(
        """
        SELECT miles FROM odometer
        WHERE vehicle_id = ? AND reading_date > ?
        ORDER BY reading_date ASC, id ASC LIMIT 1
        """,
        (vehicle_id, iso(reading_date)),
    ).fetchone()
    if following and miles > int(following["miles"]):
        raise ValueError("That reading is higher than a later reading.")
    conn.execute(
        "INSERT INTO odometer (vehicle_id, reading_date, miles, notes) VALUES (?, ?, ?, ?)",
        (vehicle_id, iso(reading_date), miles, notes.strip()[:500]),
    )
    conn.commit()


def log_service(
    conn: sqlite3.Connection,
    vehicle_id: int,
    service_date: date,
    item_key: str | None,
    mileage: int | None,
    cost_cents: int | None,
    shop: str,
    notes: str,
) -> None:
    if mileage is not None:
        log_mileage(conn, vehicle_id, service_date, mileage, notes="Logged with a service")
    conn.execute(
        """
        INSERT INTO services (vehicle_id, item_key, service_date, mileage, cost_cents, shop, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            vehicle_id,
            item_key or None,
            iso(service_date),
            mileage,
            cost_cents,
            shop.strip()[:200],
            notes.strip()[:2000],
        ),
    )
    conn.commit()


def seed_demo(conn: sqlite3.Connection, defaults: MaintenanceDefaults, today: date | None = None) -> None:
    """Fictional household. No VIN, no plate, no address, no real shop."""
    today = today or date.today()
    if conn.execute("SELECT COUNT(*) AS n FROM vehicles").fetchone()["n"]:
        return

    def add_vehicle(**fields: Any) -> int:
        cur = conn.execute(
            """
            INSERT INTO vehicles (
                nickname, make, model, model_year, fuel, vehicle_type, gvwr,
                ownership, title_date, county, is_demo, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields["nickname"],
                fields["make"],
                fields["model"],
                fields["model_year"],
                fields["fuel"],
                fields.get("vehicle_type", "passenger"),
                fields.get("gvwr"),
                fields["ownership"],
                iso(fields.get("title_date")),
                fields["county"],
                1 if fields.get("is_demo") else 0,
                iso(today),
            ),
        )
        vehicle_id = int(cur.lastrowid)
        for item in defaults.items:
            conn.execute(
                "INSERT INTO intervals (vehicle_id, item_key, miles, months) VALUES (?, ?, ?, ?)",
                (vehicle_id, item.key, item.miles, item.months),
            )
        return vehicle_id

    kia = add_vehicle(
        nickname="Demo Kia",
        make="Kia",
        model="Sportage",
        model_year=2019,
        fuel="gasoline",
        gvwr=4300,
        ownership="original_maryland",
        title_date=date(2019, 4, 2),
        county="Prince George's",
        is_demo=True,
    )
    ev = add_vehicle(
        nickname="Demo Electric",
        make="Example",
        model="EV",
        model_year=2024,
        fuel="electric",
        gvwr=4800,
        ownership="original_maryland",
        title_date=date(2024, 5, 20),
        county="Prince George's",
        is_demo=True,
    )
    for day, miles in (
        (today - timedelta(days=120), 22000),
        (today - timedelta(days=40), 23600),
        (today - timedelta(days=1), 24578),
    ):
        conn.execute(
            "INSERT INTO odometer (vehicle_id, reading_date, miles, notes) VALUES (?, ?, ?, '')",
            (kia, iso(day), miles),
        )
    conn.execute(
        "INSERT INTO odometer (vehicle_id, reading_date, miles, notes) VALUES (?, ?, ?, '')",
        (ev, iso(today - timedelta(days=3)), 8100),
    )

    def service(vehicle_id: int, key: str, when: date, miles: int | None, cost: int, shop: str, notes: str) -> None:
        conn.execute(
            """
            INSERT INTO services (vehicle_id, item_key, service_date, mileage, cost_cents, shop, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (vehicle_id, key, iso(when), miles, cost, shop, notes),
        )

    shop = "Riverside Demo Garage"
    service(kia, "oil_change", add_months(today + timedelta(days=45), -6), 21000, 8900, shop, "Fictional oil service.")
    service(
        kia,
        "engine_air_filter",
        add_months(today + timedelta(days=60), -12),
        18000,
        3200,
        shop,
        "Fictional engine air filter.",
    )
    service(
        kia,
        "cabin_air_filter",
        add_months(today + timedelta(days=20), -12),
        19000,
        2800,
        shop,
        "Fictional cabin filter.",
    )
    service(kia, "tire_rotation", add_months(today, -5), 20000, 0, shop, "Fictional rotation.")
    service(
        kia,
        "brake_inspection",
        add_months(today - timedelta(days=2), -12),
        17000,
        0,
        shop,
        "Fictional inspection, now overdue.",
    )
    service(
        kia,
        "wipers",
        add_months(today + timedelta(days=4), -12),
        20000,
        2400,
        shop,
        "Fictional wipers, due this week.",
    )
    service(kia, "battery", date(2024, 1, 15), 12000, 17500, shop, "Fictional battery.")
    service(kia, "coolant", date(2023, 6, 1), 8000, 14000, shop, "Fictional coolant.")

    veip_last = add_months(today + timedelta(days=12), -24)
    conn.execute(
        """
        INSERT INTO compliance (vehicle_id, kind, last_completed, next_due, period_years)
        VALUES (?, 'veip', ?, NULL, NULL)
        """,
        (kia, iso(veip_last)),
    )
    conn.execute(
        """
        INSERT INTO compliance (vehicle_id, kind, last_completed, next_due, period_years)
        VALUES (?, 'registration', NULL, ?, 2)
        """,
        (kia, iso(today + timedelta(days=28))),
    )
    conn.execute(
        """
        INSERT INTO compliance (vehicle_id, kind, last_completed, next_due, period_years)
        VALUES (?, 'registration', NULL, ?, 1)
        """,
        (ev, iso(today + timedelta(days=40))),
    )
    conn.commit()


def list_services(conn: sqlite3.Connection, vehicle_id: int | None = None) -> list[sqlite3.Row]:
    if vehicle_id is None:
        return conn.execute(
            """
            SELECT s.*, v.nickname FROM services s
            JOIN vehicles v ON v.id = s.vehicle_id
            ORDER BY s.service_date DESC, s.id DESC
            """
        ).fetchall()
    return conn.execute(
        """
        SELECT s.*, v.nickname FROM services s
        JOIN vehicles v ON v.id = s.vehicle_id
        WHERE s.vehicle_id = ?
        ORDER BY s.service_date DESC, s.id DESC
        """,
        (vehicle_id,),
    ).fetchall()


def list_odometer(conn: sqlite3.Connection, vehicle_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM odometer WHERE vehicle_id = ? ORDER BY reading_date DESC, id DESC",
        (vehicle_id,),
    ).fetchall()


def get_vehicle(conn: sqlite3.Connection, vehicle_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()


def save_intervals(
    conn: sqlite3.Connection,
    vehicle_id: int,
    rows: list[tuple[str, int | None, int | None]],
) -> None:
    for key, miles, months in rows:
        if miles is not None and miles < 0:
            raise ValueError("Miles interval cannot be negative.")
        if months is not None and months < 0:
            raise ValueError("Months interval cannot be negative.")
        conn.execute(
            """
            INSERT INTO intervals (vehicle_id, item_key, miles, months) VALUES (?, ?, ?, ?)
            ON CONFLICT(vehicle_id, item_key) DO UPDATE SET
                miles = excluded.miles, months = excluded.months
            """,
            (vehicle_id, key, miles, months),
        )
    conn.commit()


def save_compliance(
    conn: sqlite3.Connection,
    vehicle_id: int,
    kind: str,
    last_completed: date | None,
    next_due: date | None,
    period_years: int | None,
) -> None:
    conn.execute(
        """
        INSERT INTO compliance (vehicle_id, kind, last_completed, next_due, period_years)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(vehicle_id, kind) DO UPDATE SET
            last_completed = excluded.last_completed,
            next_due = excluded.next_due,
            period_years = excluded.period_years
        """,
        (vehicle_id, kind, iso(last_completed), iso(next_due), period_years),
    )
    conn.commit()


def add_vehicle(conn: sqlite3.Connection, defaults: MaintenanceDefaults, fields: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO vehicles (
            nickname, make, model, model_year, fuel, vehicle_type, gvwr,
            ownership, title_date, county, is_demo, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            fields["nickname"].strip(),
            fields["make"].strip(),
            fields["model"].strip(),
            int(fields["model_year"]),
            fields["fuel"],
            fields.get("vehicle_type") or "passenger",
            fields.get("gvwr"),
            fields["ownership"],
            iso(fields.get("title_date")),
            fields["county"].strip(),
            iso(date.today()),
        ),
    )
    vehicle_id = int(cur.lastrowid)
    for item in defaults.items:
        conn.execute(
            "INSERT INTO intervals (vehicle_id, item_key, miles, months) VALUES (?, ?, ?, ?)",
            (vehicle_id, item.key, item.miles, item.months),
        )
    if fields.get("registration_due"):
        conn.execute(
            """
            INSERT INTO compliance (vehicle_id, kind, last_completed, next_due, period_years)
            VALUES (?, 'registration', NULL, ?, ?)
            """,
            (vehicle_id, iso(fields["registration_due"]), fields.get("period_years")),
        )
    conn.commit()
    return vehicle_id


def update_vehicle(conn: sqlite3.Connection, vehicle_id: int, fields: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE vehicles SET
            nickname = ?, make = ?, model = ?, model_year = ?, fuel = ?,
            vehicle_type = ?, gvwr = ?, ownership = ?, title_date = ?, county = ?
        WHERE id = ?
        """,
        (
            fields["nickname"].strip(),
            fields["make"].strip(),
            fields["model"].strip(),
            int(fields["model_year"]),
            fields["fuel"],
            fields.get("vehicle_type") or "passenger",
            fields.get("gvwr"),
            fields["ownership"],
            iso(fields.get("title_date")),
            fields["county"].strip(),
            vehicle_id,
        ),
    )
    conn.commit()


def delete_vehicle(conn: sqlite3.Connection, vehicle_id: int) -> None:
    conn.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))
    conn.commit()
