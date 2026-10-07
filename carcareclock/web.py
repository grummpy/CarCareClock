"""Local web UI. It binds to 127.0.0.1 only."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from flask import Flask, flash, g, redirect, render_template, request, send_from_directory, url_for

from carcareclock.db import connect, init_db
from carcareclock.ics_export import build_calendar
from carcareclock.paths import assets_dir
from carcareclock.rules import MaintenanceDefaults, MarylandRules
from carcareclock.schedule import format_long_date
from carcareclock.service import (
    add_vehicle,
    all_items,
    calendar_items,
    delete_vehicle,
    get_vehicle,
    list_odometer,
    list_services,
    log_mileage,
    log_service,
    reminder_window_days,
    save_compliance,
    save_intervals,
    seed_demo,
    set_reminder_window_days,
    timeline,
    update_vehicle,
    vehicle_cards,
)

FUELS = ("gasoline", "diesel", "electric", "hybrid")
OWNERSHIP = (
    ("original_maryland", "Original Maryland owner"),
    ("lease_buyout_original_lessee", "Lease buyout, original lessee"),
    ("used", "Used, or previously titled elsewhere"),
)
VEHICLE_TYPES = (
    "passenger",
    "motorcycle",
    "farm",
    "historic",
    "fire_apparatus",
    "ambulance",
    "street_rod",
    "military_tactical",
    "school_bus",
    "passenger_bus",
)


def create_app(
    db_path: Path,
    rules: MarylandRules,
    defaults: MaintenanceDefaults,
    secret_key: str = "carcareclock-local",
) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["SECRET_KEY"] = secret_key
    app.config["DB_PATH"] = str(db_path)
    app.config["RULES"] = rules
    app.config["DEFAULTS"] = defaults

    startup = connect(db_path)
    init_db(startup)
    seed_demo(startup, defaults)
    startup.close()

    @app.before_request
    def open_db() -> None:
        g.db = connect(Path(app.config["DB_PATH"]))

    @app.teardown_request
    def close_db(_exc: BaseException | None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.context_processor
    def inject_nav() -> dict[str, Any]:
        return {"verify_note": rules.verify_with_mva, "county_label": county_label}

    @app.get("/")
    def dashboard():
        today = date.today()
        items = all_items(g.db, rules, defaults, today)
        reminders = [item for item in items if item.status in {"overdue", "due_soon"}]
        reminders.sort(key=lambda item: (item.due or today, item.vehicle_name))
        vehicles = g.db.execute("SELECT id, nickname FROM vehicles ORDER BY id").fetchall()
        return render_template(
            "dashboard.html",
            cards=vehicle_cards(g.db, rules, defaults, today),
            reminders=reminders,
            timeline=timeline(items, today),
            window_days=reminder_window_days(g.db),
            vehicles=vehicles,
            today=today.isoformat(),
            generic_note=defaults.note,
        )

    @app.post("/mileage")
    def post_mileage():
        try:
            log_mileage(
                g.db,
                int(request.form["vehicle_id"]),
                _date(request.form["reading_date"]),
                _int(request.form["miles"], "miles"),
            )
        except (ValueError, KeyError) as exc:
            flash(str(exc) or "Could not log that reading.", "error")
        else:
            flash("Mileage logged.", "ok")
        return redirect(url_for("dashboard"))

    @app.post("/settings")
    def post_settings():
        try:
            set_reminder_window_days(g.db, _int(request.form["window_days"], "window"))
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            flash("Reminder window saved.", "ok")
        return redirect(url_for("dashboard"))

    @app.get("/history")
    def history():
        labels = {item.key: item.label for item in defaults.items}
        return render_template(
            "history.html",
            services=list_services(g.db),
            money=_money,
            labels=labels,
        )

    @app.get("/rules")
    def rules_page():
        return render_template("rules.html", rules=rules, defaults=defaults)

    @app.get("/export.ics")
    def export_ics():
        today = date.today()
        items = calendar_items(all_items(g.db, rules, defaults, today), today, rules.verify_with_mva)
        payload = build_calendar(items, alarm_days=reminder_window_days(g.db))
        return app.response_class(
            payload,
            mimetype="text/calendar",
            headers={"Content-Disposition": "attachment; filename=carcareclock.ics"},
        )

    @app.get("/vehicle/new")
    def new_vehicle():
        return render_template(
            "vehicle_form.html",
            vehicle=None,
            fuels=FUELS,
            ownership=OWNERSHIP,
            vehicle_types=VEHICLE_TYPES,
            periods=sorted(rules.registration_periods_allowed()),
            default_period=rules.registration_default_period_years,
        )

    @app.post("/vehicle/new")
    def post_new_vehicle():
        try:
            fields = _vehicle_fields(rules)
            vehicle_id = add_vehicle(g.db, defaults, fields)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("new_vehicle"))
        flash("Vehicle added. Generic placeholder intervals were copied for you to edit.", "ok")
        return redirect(url_for("vehicle", vehicle_id=vehicle_id))

    @app.get("/vehicle/<int:vehicle_id>")
    def vehicle(vehicle_id: int):
        row = get_vehicle(g.db, vehicle_id)
        if row is None:
            flash("That vehicle is not in the local database.", "error")
            return redirect(url_for("dashboard"))
        today = date.today()
        items = all_items(g.db, rules, defaults, today)
        mine = [item for item in items if item.vehicle_id == vehicle_id]
        intervals = g.db.execute(
            "SELECT item_key, miles, months FROM intervals WHERE vehicle_id = ? ORDER BY item_key",
            (vehicle_id,),
        ).fetchall()
        labels = {item.key: item.label for item in defaults.items}
        compliance = {
            record["kind"]: record
            for record in g.db.execute(
                "SELECT * FROM compliance WHERE vehicle_id = ?", (vehicle_id,)
            ).fetchall()
        }
        return render_template(
            "vehicle.html",
            vehicle=row,
            items=mine,
            intervals=intervals,
            labels=labels,
            compliance=compliance,
            services=list_services(g.db, vehicle_id),
            readings=list_odometer(g.db, vehicle_id),
            fuels=FUELS,
            ownership=OWNERSHIP,
            vehicle_types=VEHICLE_TYPES,
            periods=sorted(rules.registration_periods_allowed()),
            primary_periods=list(rules.registration_periods_years),
            generic_note=defaults.note,
            money=_money,
            long_date=format_long_date,
            item_keys=[item.key for item in defaults.items],
            today=today.isoformat(),
        )

    @app.post("/vehicle/<int:vehicle_id>")
    def post_vehicle(vehicle_id: int):
        if get_vehicle(g.db, vehicle_id) is None:
            return redirect(url_for("dashboard"))
        try:
            update_vehicle(g.db, vehicle_id, _vehicle_fields(rules))
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            flash("Vehicle saved.", "ok")
        return redirect(url_for("vehicle", vehicle_id=vehicle_id))

    @app.post("/vehicle/<int:vehicle_id>/intervals")
    def post_intervals(vehicle_id: int):
        rows = []
        for key in request.form.getlist("item_key"):
            rows.append(
                (
                    key,
                    _optional_int(request.form.get(f"miles_{key}", "")),
                    _optional_int(request.form.get(f"months_{key}", "")),
                )
            )
        try:
            save_intervals(g.db, vehicle_id, rows)
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            flash("Intervals saved for this vehicle.", "ok")
        return redirect(url_for("vehicle", vehicle_id=vehicle_id))

    @app.post("/vehicle/<int:vehicle_id>/compliance")
    def post_compliance(vehicle_id: int):
        try:
            period_text = request.form.get("period_years", "").strip()
            period = int(period_text) if period_text else None
            if period is not None and period not in rules.registration_periods_allowed():
                raise ValueError("That registration period is not in the rules file.")
            save_compliance(
                g.db,
                vehicle_id,
                "veip",
                _optional_date(request.form.get("veip_last", "")),
                _optional_date(request.form.get("veip_due", "")),
                None,
            )
            save_compliance(
                g.db,
                vehicle_id,
                "registration",
                None,
                _optional_date(request.form.get("registration_due", "")),
                period,
            )
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            flash("Emissions and registration dates saved.", "ok")
        return redirect(url_for("vehicle", vehicle_id=vehicle_id))

    @app.post("/vehicle/<int:vehicle_id>/service")
    def post_service(vehicle_id: int):
        try:
            item = request.form.get("item_key", "").strip() or None
            log_service(
                g.db,
                vehicle_id,
                _date(request.form["service_date"]),
                item,
                _optional_int(request.form.get("mileage", "")),
                _money_to_cents(request.form.get("cost", "")),
                request.form.get("shop", ""),
                request.form.get("notes", ""),
            )
        except (ValueError, KeyError) as exc:
            flash(str(exc) or "Could not save that service.", "error")
        else:
            flash("Service logged.", "ok")
        return redirect(url_for("vehicle", vehicle_id=vehicle_id))

    @app.post("/vehicle/<int:vehicle_id>/delete")
    def post_delete(vehicle_id: int):
        if request.form.get("confirm") != "yes":
            flash("Check the box to remove the vehicle.", "error")
            return redirect(url_for("vehicle", vehicle_id=vehicle_id))
        delete_vehicle(g.db, vehicle_id)
        flash("Vehicle removed from this computer.", "ok")
        return redirect(url_for("dashboard"))

    @app.get("/favicon.ico")
    def favicon():
        return send_from_directory(assets_dir(), "icon.ico")

    @app.get("/assets/<path:name>")
    def asset(name: str):
        return send_from_directory(assets_dir(), name)

    return app


def county_label(county: str | None) -> str:
    text = (county or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if "county" in lowered or lowered.endswith(" city"):
        return text
    return f"{text} County"


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Enter a real date.") from exc


def _optional_date(value: str | None) -> date | None:
    if value is None or not value.strip():
        return None
    return _date(value.strip())


def _int(value: str, label: str) -> int:
    text = value.strip().replace(",", "")
    if not text.isdigit():
        raise ValueError(f"{label[:1].upper()}{label[1:]} must be a whole number.")
    return int(text)


def _optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return _int(value, "interval")


def _money_to_cents(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        amount = Decimal(value.strip())
    except InvalidOperation as exc:
        raise ValueError("Cost must be a dollar amount.") from exc
    if amount < 0:
        raise ValueError("Cost cannot be negative.")
    cents = (amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _money(cents: int | None) -> str:
    if cents is None:
        return "—"
    return f"${cents / 100:,.2f}"


def _vehicle_fields(rules: MarylandRules) -> dict:
    nickname = request.form.get("nickname", "").strip()
    make = request.form.get("make", "").strip()
    model = request.form.get("model", "").strip()
    county = request.form.get("county", "").strip()
    if not nickname or not make or not model or not county:
        raise ValueError("Nickname, make, model, and county are required.")
    fuel = request.form.get("fuel", "")
    if fuel not in FUELS:
        raise ValueError("Pick a fuel type.")
    ownership = request.form.get("ownership", "")
    if ownership not in {key for key, _label in OWNERSHIP}:
        raise ValueError("Pick an ownership type.")
    vehicle_type = request.form.get("vehicle_type", "passenger")
    if vehicle_type not in VEHICLE_TYPES:
        raise ValueError("Pick a vehicle type.")
    gvwr_text = request.form.get("gvwr", "").strip()
    period_text = request.form.get("period_years", "").strip()
    period = int(period_text) if period_text else rules.registration_default_period_years
    if period not in rules.registration_periods_allowed():
        raise ValueError("That registration period is not in the rules file.")
    return {
        "nickname": nickname,
        "make": make,
        "model": model,
        "model_year": _int(request.form.get("model_year", ""), "model year"),
        "fuel": fuel,
        "vehicle_type": vehicle_type,
        "gvwr": _int(gvwr_text, "GVWR") if gvwr_text else None,
        "ownership": ownership,
        "title_date": _optional_date(request.form.get("title_date")),
        "county": county,
        "registration_due": _optional_date(request.form.get("registration_due")),
        "period_years": period,
    }

