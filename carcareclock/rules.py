"""Load Maryland planning rules and generic maintenance defaults from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class RulesError(ValueError):
    """The YAML is missing a field the planner needs."""


def _need(data: dict[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise RulesError(f"{where} is missing '{key}'")
    return data[key]


@dataclass(frozen=True)
class MaintenanceItemDefault:
    key: str
    label: str
    miles: int | None
    months: int | None


@dataclass(frozen=True)
class MaintenanceDefaults:
    note: str
    items: tuple[MaintenanceItemDefault, ...]

    def by_key(self) -> dict[str, MaintenanceItemDefault]:
        return {item.key: item for item in self.items}


@dataclass(frozen=True)
class MarylandRules:
    """Every dated MVA figure the planner uses comes from this object."""

    verify_with_mva: str
    checked_on: str
    raw: dict[str, Any]
    veip_cycle_months: int
    new_model_year_min: int
    new_exempt_months: int
    new_anchor: str
    qualifying_ownership: tuple[str, ...]
    email_weeks_before_due: int
    mail_weeks_before_due_min: int
    mail_weeks_before_due_max: int
    late_fee_usd: int
    late_fee_repeat_days: int
    test_fee_station_usd: int
    test_fee_kiosk_usd: int
    used_purchase_notice_months: int
    apply_used_purchase_notice_as_due_date: bool
    counties: tuple[str, ...]
    hybrids_required_after_window: bool
    exemptions: tuple[dict[str, Any], ...]
    registration_periods_years: tuple[int, ...]
    registration_also_offered_years: tuple[int, ...]
    registration_default_period_years: int
    early_renew_days: int
    planning_deadline: str
    registration_notice_lead_days: int | None
    registration_notice_statement: str
    mail_must_arrive_days: int
    flag_email_days: int

    def registration_periods_allowed(self) -> set[int]:
        return set(self.registration_periods_years) | set(self.registration_also_offered_years)


def load_rules(path: Path) -> MarylandRules:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RulesError(f"{path} is not a mapping")
    note = str(_need(data, "verify_with_mva", str(path))).strip()
    lowered = note.lower()
    if "verify with mva" not in lowered:
        raise RulesError(f"{path} must include a 'verify with MVA' note")
    veip = _need(data, "veip", str(path))
    new = _need(veip, "new_vehicle", "veip")
    notice = _need(veip, "notice", "veip")
    late = _need(veip, "late_fee", "veip")
    reg = _need(data, "registration", str(path))
    reg_notice = _need(reg, "notice", "registration")
    anchor = str(_need(new, "anchor", "veip.new_vehicle"))
    if anchor not in {"model_year_start", "title_date"}:
        raise RulesError("veip.new_vehicle.anchor must be model_year_start or title_date")
    deadline = str(_need(reg, "planning_deadline", "registration"))
    if deadline not in {"card_date", "last_day_of_month_on_card"}:
        raise RulesError("registration.planning_deadline is not a known mode")
    lead = reg_notice.get("published_lead_time_days")
    return MarylandRules(
        verify_with_mva=note,
        checked_on=str(_need(data, "checked_on", str(path))),
        raw=data,
        veip_cycle_months=int(_need(veip, "cycle_months", "veip")),
        new_model_year_min=int(_need(new, "model_year_min", "veip.new_vehicle")),
        new_exempt_months=int(_need(new, "exempt_months", "veip.new_vehicle")),
        new_anchor=anchor,
        qualifying_ownership=tuple(str(x) for x in _need(new, "qualifying_ownership", "veip.new_vehicle")),
        email_weeks_before_due=int(_need(notice, "email_weeks_before_due", "veip.notice")),
        mail_weeks_before_due_min=int(_need(notice, "mail_weeks_before_due_min", "veip.notice")),
        mail_weeks_before_due_max=int(_need(notice, "mail_weeks_before_due_max", "veip.notice")),
        late_fee_usd=int(_need(late, "amount_usd", "veip.late_fee")),
        late_fee_repeat_days=int(_need(late, "repeat_every_days", "veip.late_fee")),
        test_fee_station_usd=int(_need(veip, "test_fee_station_usd", "veip")),
        test_fee_kiosk_usd=int(_need(veip, "test_fee_kiosk_usd", "veip")),
        used_purchase_notice_months=int(_need(veip, "used_purchase_notice_months", "veip")),
        apply_used_purchase_notice_as_due_date=bool(
            _need(veip, "apply_used_purchase_notice_as_due_date", "veip")
        ),
        counties=tuple(str(x) for x in _need(veip, "counties", "veip")),
        hybrids_required_after_window=bool(
            _need(veip, "hybrids_required_after_new_vehicle_window", "veip")
        ),
        exemptions=tuple(_need(veip, "exemptions", "veip")),
        registration_periods_years=tuple(int(x) for x in _need(reg, "periods_years", "registration")),
        registration_also_offered_years=tuple(
            int(x) for x in _need(reg, "also_offered_years", "registration")
        ),
        registration_default_period_years=int(_need(reg, "default_period_years", "registration")),
        early_renew_days=int(_need(reg, "early_renew_days_before_expiration", "registration")),
        planning_deadline=deadline,
        registration_notice_lead_days=None if lead is None else int(lead),
        registration_notice_statement=str(_need(reg_notice, "statement", "registration.notice")),
        mail_must_arrive_days=int(
            _need(reg_notice, "mail_must_arrive_days_before_expiration", "registration.notice")
        ),
        flag_email_days=int(
            _need(reg_notice, "flag_email_days_before_expiration", "registration.notice")
        ),
    )


def load_defaults(path: Path) -> MaintenanceDefaults:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RulesError(f"{path} is not a mapping")
    note = str(_need(data, "note", str(path))).strip()
    items: list[MaintenanceItemDefault] = []
    for raw in _need(data, "items", str(path)):
        miles = raw.get("miles")
        months = raw.get("months")
        items.append(
            MaintenanceItemDefault(
                key=str(raw["key"]),
                label=str(raw["label"]),
                miles=None if miles is None else int(miles),
                months=None if months is None else int(months),
            )
        )
    if not items:
        raise RulesError(f"{path} has no maintenance items")
    return MaintenanceDefaults(note=note, items=tuple(items))
