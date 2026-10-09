"""VEIP and registration dates come from rules/maryland.yaml, not from constants."""

from datetime import date, timedelta
from pathlib import Path

import yaml

from carcareclock.db import connect, init_db
from carcareclock.rules import load_defaults, load_rules
from carcareclock.schedule import (
    add_years,
    assess_registration,
    assess_veip,
    month_end,
    veip_late_fee_usd,
    veip_notice_window,
)
from carcareclock.service import calendar_items, items_for_vehicle

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "maryland.yaml"


def test_shipped_yaml_matches_the_researched_mva_figures():
    rules = load_rules(RULES)
    assert "verify with mva" in rules.verify_with_mva.lower()
    assert rules.checked_on == "2026-10-07"
    assert rules.veip_cycle_months == 24
    assert rules.new_model_year_min == 2019
    assert rules.new_exempt_months == 72
    assert rules.new_anchor == "model_year_start"
    assert rules.email_weeks_before_due == 8
    assert (rules.mail_weeks_before_due_min, rules.mail_weeks_before_due_max) == (6, 8)
    assert rules.late_fee_usd == 30
    assert rules.late_fee_repeat_days == 28
    assert "Prince George's" in rules.counties
    assert rules.registration_periods_years == (1, 2)
    assert 3 in rules.registration_also_offered_years
    assert rules.early_renew_days == 90
    assert rules.registration_notice_lead_days is None
    assert rules.mail_must_arrive_days == 15
    assert rules.flag_email_days == 70
    assert rules.planning_deadline == "card_date"
    assert rules.used_purchase_notice_months == 4
    assert rules.apply_used_purchase_notice_as_due_date is False


def test_cycle_and_new_vehicle_window_follow_the_yaml(tmp_path: Path):
    rules = load_rules(RULES)
    used = {
        "county": "Prince George's County",
        "fuel": "gasoline",
        "vehicle_type": "passenger",
        "model_year": 2016,
        "gvwr": 4000,
        "ownership": "used",
        "title_date": date(2024, 1, 1),
        "last_completed": date(2024, 6, 15),
        "next_due": None,
    }
    planned = assess_veip(used, rules, date(2026, 1, 1))
    assert planned.due == date(2026, 6, 15)
    assert planned.due_source == "cycle"
    assert planned.exempt is False

    new = {
        "county": "Prince George's",
        "fuel": "gasoline",
        "vehicle_type": "passenger",
        "model_year": 2022,
        "gvwr": 4300,
        "ownership": "original_maryland",
        "title_date": date(2022, 6, 15),
        "last_completed": None,
        "next_due": None,
    }
    still_new = assess_veip(new, rules, date(2026, 10, 7))
    assert still_new.first_test == date(2028, 1, 1)
    assert still_new.exempt is True
    assert still_new.due == date(2028, 1, 1)

    edited = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    edited["veip"]["cycle_months"] = 12
    edited["veip"]["new_vehicle"]["exempt_months"] = 36
    edited["veip"]["new_vehicle"]["anchor"] = "title_date"
    path = tmp_path / "maryland.yaml"
    path.write_text(yaml.safe_dump(edited), encoding="utf-8")
    custom = load_rules(path)
    assert assess_veip(used, custom, date(2026, 1, 1)).due == date(2025, 6, 15)
    retitled = assess_veip(new, custom, date(2024, 1, 1))
    assert retitled.first_test == date(2025, 6, 15)
    assert retitled.due_source == "new_vehicle_anchor"


def test_estimated_first_veip_is_visible_during_the_reminder_window(tmp_path: Path):
    rules = load_rules(RULES)
    defaults = load_defaults(ROOT / "rules" / "maintenance_defaults.yaml")
    conn = connect(tmp_path / "synthetic.sqlite")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO vehicles (
            nickname, make, model, model_year, fuel, vehicle_type, gvwr,
            ownership, title_date, county, is_demo, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Synthetic new vehicle",
            "Example",
            "Model",
            2022,
            "gasoline",
            "passenger",
            4000,
            "original_maryland",
            None,
            "Prince George's",
            1,
            "2026-01-01",
        ),
    )
    conn.commit()
    vehicle = conn.execute("SELECT * FROM vehicles").fetchone()
    due = date(2028, 1, 1)
    views = items_for_vehicle(conn, vehicle, rules, defaults, due - timedelta(days=7), 7)
    veip = next(item for item in views if item.key == "veip")
    assert veip.status == "due_soon"
    assert "Estimated first test" in veip.detail
    assert calendar_items([veip], due - timedelta(days=7), "Verify with MVA.")
    before = items_for_vehicle(conn, vehicle, rules, defaults, due - timedelta(days=8), 7)
    assert next(item for item in before if item.key == "veip").status == "exempt"
    conn.close()


def test_exemptions_and_county_come_from_the_yaml():
    rules = load_rules(RULES)
    base = {
        "county": "Prince George's",
        "fuel": "gasoline",
        "vehicle_type": "passenger",
        "model_year": 2010,
        "gvwr": 4000,
        "ownership": "used",
        "title_date": None,
        "last_completed": None,
        "next_due": None,
    }
    old = dict(base, model_year=1995, gvwr=4000)
    assert assess_veip(old, rules, date(2026, 1, 1)).exemption_id == "model_year_1995_or_older_under_8500"
    heavy_old = dict(base, model_year=1995, gvwr=9000)
    assert assess_veip(heavy_old, rules, date(2026, 1, 1)).exempt is False
    assert assess_veip(dict(base, fuel="electric"), rules, date(2026, 1, 1)).exemption_id == "electric_only"
    assert assess_veip(dict(base, fuel="diesel"), rules, date(2026, 1, 1)).exemption_id == "diesel_only"
    assert assess_veip(dict(base, vehicle_type="motorcycle"), rules, date(2026, 1, 1)).exempt
    hybrid = dict(
        base,
        fuel="hybrid",
        model_year=2010,
        ownership="original_maryland",
        next_due=date(2026, 6, 1),
    )
    assessed = assess_veip(hybrid, rules, date(2026, 1, 1))
    assert assessed.exempt is False
    assert assessed.due == date(2026, 6, 1)
    outside = assess_veip(dict(base, county="Garrett"), rules, date(2026, 1, 1))
    assert outside.required is False


def test_notice_window_and_late_fee_follow_the_yaml(tmp_path: Path):
    rules = load_rules(RULES)
    due = date(2026, 6, 5)
    window = veip_notice_window(due, rules)
    assert window.email_on == due - timedelta(weeks=8)
    assert window.mail_opens == due - timedelta(weeks=8)
    assert window.mail_closes == due - timedelta(weeks=6)
    assert window.email_on == date(2026, 4, 10)
    assert window.mail_closes == date(2026, 4, 24)

    assert veip_late_fee_usd(due, due, rules) == 0
    assert veip_late_fee_usd(due, due + timedelta(days=1), rules) == 30
    assert veip_late_fee_usd(due, due + timedelta(days=1 + 27), rules) == 30
    assert veip_late_fee_usd(due, due + timedelta(days=1 + 28), rules) == 60

    edited = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    edited["veip"]["late_fee"]["amount_usd"] = 15
    edited["veip"]["late_fee"]["repeat_every_days"] = 10
    edited["veip"]["notice"]["email_weeks_before_due"] = 4
    path = tmp_path / "maryland.yaml"
    path.write_text(yaml.safe_dump(edited), encoding="utf-8")
    custom = load_rules(path)
    assert veip_late_fee_usd(due, due + timedelta(days=1), custom) == 15
    assert veip_late_fee_usd(due, due + timedelta(days=11), custom) == 30
    assert veip_notice_window(due, custom).email_on == due - timedelta(weeks=4)


def test_registration_periods_and_notice_timing_follow_the_yaml(tmp_path: Path):
    rules = load_rules(RULES)
    card = date(2026, 6, 21)
    one = assess_registration(card, 1, rules)
    two = assess_registration(card, 2, rules)
    three = assess_registration(card, 3, rules)
    assert one.next_after_renewal == date(2027, 6, 21)
    assert two.next_after_renewal == date(2028, 6, 21)
    assert three.next_after_renewal == date(2029, 6, 21)
    assert two.planning_due == card
    assert two.month_end == date(2026, 6, 30)
    assert two.early_renew_opens == card - timedelta(days=90)
    assert two.published_notice_on is None
    assert two.mail_deadline == card - timedelta(days=15)
    assert two.flag_email_on == card - timedelta(days=70)
    try:
        assess_registration(card, 4, rules)
    except ValueError:
        pass
    else:
        raise AssertionError("a 4-year period is not in the rules file")

    leap = date(2024, 2, 29)
    assert add_years(leap, 1) == date(2025, 2, 28)

    edited = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    edited["registration"]["periods_years"] = [1]
    edited["registration"]["also_offered_years"] = []
    edited["registration"]["early_renew_days_before_expiration"] = 45
    edited["registration"]["planning_deadline"] = "last_day_of_month_on_card"
    edited["registration"]["notice"]["published_lead_time_days"] = 20
    path = tmp_path / "maryland.yaml"
    path.write_text(yaml.safe_dump(edited), encoding="utf-8")
    custom = load_rules(path)
    planned = assess_registration(card, 1, custom)
    assert planned.planning_due == month_end(card)
    assert planned.early_renew_opens == card - timedelta(days=45)
    assert planned.published_notice_on == card - timedelta(days=20)
    try:
        assess_registration(card, 2, custom)
    except ValueError:
        pass
    else:
        raise AssertionError("2 years was removed from the YAML and must be rejected")
