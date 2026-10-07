"""Due dates: whichever interval comes first, mileage projection, MVA rules, reminders.

Date math uses calendar days. A daylight-saving transition does not add or drop
a day, because nothing here converts a span into a fixed number of hours.
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from carcareclock.rules import MarylandRules

NEW_YORK = ZoneInfo("America/New_York")


def add_months(day: date, months: int) -> date:
    index = day.month - 1 + months
    year = day.year + index // 12
    month = index % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def add_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def month_end(day: date) -> date:
    last = calendar.monthrange(day.year, day.month)[1]
    return date(day.year, day.month, last)


def miles_per_day(
    readings: list[tuple[date, int]],
    window_days: int = 180,
) -> float | None:
    """Miles per calendar day between the oldest and newest reading in the window.

    The window is measured back from the latest reading. With fewer than two
    readings inside it, the last two readings are used. A zero-day span or a
    falling odometer returns None.
    """
    if len(readings) < 2:
        return None
    ordered = sorted(readings, key=lambda row: (row[0], row[1]))
    latest = ordered[-1][0]
    recent = [row for row in ordered if (latest - row[0]).days <= window_days]
    if len(recent) < 2:
        recent = ordered[-2:]
    start, end = recent[0], recent[-1]
    days = (end[0] - start[0]).days
    if days <= 0:
        return None
    delta = end[1] - start[1]
    if delta < 0:
        return None
    return delta / days


def project_mileage_date(
    anchor: date,
    miles_remaining: int,
    rate_per_day: float,
) -> date | None:
    """Calendar date when the remaining miles run out, counted from `anchor`.

    `anchor` is the date of the latest odometer reading. The result is that
    date plus a whole number of calendar days, so a 23-hour daylight-saving
    day still counts as one day.
    """
    if rate_per_day <= 0:
        return None
    if miles_remaining <= 0:
        return anchor
    days = math.ceil(miles_remaining / rate_per_day)
    return anchor + timedelta(days=days)


@dataclass(frozen=True)
class IntervalDue:
    due: date | None
    reason: str | None
    needs_readings: bool = False

    @property
    def has_date(self) -> bool:
        return self.due is not None


def whichever_comes_first(
    *,
    last_date: date | None,
    last_miles: int | None,
    months_interval: int | None,
    miles_interval: int | None,
    readings: list[tuple[date, int]],
    today: date,
) -> IntervalDue:
    """Earlier of the months anniversary and the projected mileage date.

    A blank interval is ignored. If the only interval is mileage and there is
    no usable rate yet, and the odometer has not already passed the target,
    the result has no date and `needs_readings` is true.
    """
    candidates: list[tuple[date, str]] = []
    needs_readings = False
    if months_interval is not None and last_date is not None:
        candidates.append((add_months(last_date, months_interval), "months"))

    current = readings[-1][1] if readings else None
    anchor = readings[-1][0] if readings else today
    if miles_interval is not None and last_miles is not None and current is not None:
        target = last_miles + miles_interval
        remaining = target - current
        if remaining <= 0:
            candidates.append((anchor, "miles"))
        else:
            rate = miles_per_day(readings)
            projected = project_mileage_date(anchor, remaining, rate) if rate else None
            if projected is None:
                needs_readings = True
            else:
                candidates.append((projected, "miles"))
    elif miles_interval is not None and (last_miles is None or current is None):
        needs_readings = True

    if not candidates:
        return IntervalDue(due=None, reason=None, needs_readings=needs_readings)
    candidates.sort(key=lambda item: item[0])
    first_day = candidates[0][0]
    reasons = [reason for day, reason in candidates if day == first_day]
    reason = "both" if len(reasons) > 1 else reasons[0]
    return IntervalDue(due=first_day, reason=reason, needs_readings=False)


def reminder_status(due: date | None, today: date, window_days: int) -> str:
    """`overdue` and `due_soon` are the dashboard reminder list.

    `due_soon` includes today and the next `window_days` days. A due date
    `window_days + 1` days out is only `upcoming`.
    """
    if due is None:
        return "needs_date"
    delta = (due - today).days
    if delta < 0:
        return "overdue"
    if delta <= window_days:
        return "due_soon"
    return "upcoming"


def in_reminder_window(due: date, today: date, window_days: int) -> bool:
    return reminder_status(due, today, window_days) in {"overdue", "due_soon"}


def due_phrase(due: date | None, today: date) -> str:
    if due is None:
        return "Needs a date"
    delta = (due - today).days
    if delta == 0:
        return "Due today"
    if delta == 1:
        return "Due in 1 day"
    if delta > 1:
        return f"Due in {delta} days"
    if delta == -1:
        return "1 day overdue"
    return f"{-delta} days overdue"


def format_long_date(day: date) -> str:
    return f"{day.strftime('%b')} {day.day}, {day.year}"


def _norm_county(value: str) -> str:
    text = value.lower().replace("county", " ")
    text = text.replace("'", "").replace("’", "").replace(".", " ")
    return " ".join(text.split())


def county_requires_veip(county: str, rules: MarylandRules) -> bool:
    wanted = _norm_county(county)
    return any(_norm_county(name) == wanted for name in rules.counties)


def _matches_exemption(vehicle: dict[str, Any], rule: dict[str, Any]) -> bool:
    if "model_year_on_or_before" in rule:
        year = vehicle.get("model_year")
        gvwr = vehicle.get("gvwr")
        if year is None or gvwr is None:
            return False
        if int(year) > int(rule["model_year_on_or_before"]):
            return False
        if int(gvwr) >= int(rule["gvwr_under"]):
            return False
        return True
    if "gvwr_over" in rule:
        gvwr = vehicle.get("gvwr")
        return gvwr is not None and int(gvwr) > int(rule["gvwr_over"])
    if "fuel" in rule:
        fuel = str(vehicle.get("fuel") or "").lower()
        return fuel == str(rule["fuel"]).lower()
    if "vehicle_type" in rule:
        wanted = rule["vehicle_type"]
        actual = str(vehicle.get("vehicle_type") or "").lower()
        if isinstance(wanted, list):
            return actual in {str(item).lower() for item in wanted}
        return actual == str(wanted).lower()
    return False


def hard_exemption(vehicle: dict[str, Any], rules: MarylandRules) -> str | None:
    for rule in rules.exemptions:
        if _matches_exemption(vehicle, rule):
            return str(rule["id"])
    return None


def new_vehicle_first_test(vehicle: dict[str, Any], rules: MarylandRules) -> date | None:
    """First VEIP date for a qualifying new vehicle, or None if it does not qualify."""
    year = vehicle.get("model_year")
    if year is None or int(year) < rules.new_model_year_min:
        return None
    ownership = str(vehicle.get("ownership") or "")
    if ownership not in rules.qualifying_ownership:
        return None
    if rules.new_anchor == "title_date":
        title = vehicle.get("title_date")
        if title is None:
            return None
        return add_months(title, rules.new_exempt_months)
    return add_months(date(int(year), 1, 1), rules.new_exempt_months)


@dataclass(frozen=True)
class NoticeWindow:
    due: date
    email_on: date
    mail_opens: date
    mail_closes: date

    @property
    def email_weeks(self) -> int:
        return (self.due - self.email_on).days // 7


def veip_notice_window(due: date, rules: MarylandRules) -> NoticeWindow:
    """Span from the MVA notice to the test due date, using the YAML week counts."""
    return NoticeWindow(
        due=due,
        email_on=due - timedelta(weeks=rules.email_weeks_before_due),
        mail_opens=due - timedelta(weeks=rules.mail_weeks_before_due_max),
        mail_closes=due - timedelta(weeks=rules.mail_weeks_before_due_min),
    )


def veip_late_fee_usd(due: date, as_of: date, rules: MarylandRules) -> int:
    """$0 through the due date. The YAML amount posts the next day, then every N days.

    "The next day" is `due + 1`. "Every `repeat_every_days` thereafter" counts
    from that first assessment day, not from the due date.
    """
    first = due + timedelta(days=1)
    if as_of < first:
        return 0
    periods = 1 + (as_of - first).days // rules.late_fee_repeat_days
    return periods * rules.late_fee_usd


@dataclass(frozen=True)
class VeipAssessment:
    required: bool
    exempt: bool
    exemption_id: str | None
    due: date | None
    due_source: str
    notice: NoticeWindow | None
    late_fee_usd: int
    first_test: date | None
    detail: str


def assess_veip(vehicle: dict[str, Any], rules: MarylandRules, as_of: date) -> VeipAssessment:
    """Plan a VEIP date from the YAML. An entered notice date wins over the estimate."""
    if not county_requires_veip(str(vehicle.get("county") or ""), rules):
        return VeipAssessment(
            required=False,
            exempt=False,
            exemption_id=None,
            due=None,
            due_source="county",
            notice=None,
            late_fee_usd=0,
            first_test=None,
            detail="This county is not on the VEIP county list in the rules file.",
        )
    exemption = hard_exemption(vehicle, rules)
    if exemption:
        return VeipAssessment(
            required=True,
            exempt=True,
            exemption_id=exemption,
            due=None,
            due_source="exemption",
            notice=None,
            late_fee_usd=0,
            first_test=None,
            detail=f"Exempt under the rules file ({exemption}). Verify with MVA.",
        )
    first = new_vehicle_first_test(vehicle, rules)
    override = vehicle.get("next_due")
    last = vehicle.get("last_completed")
    if override is not None:
        due = override
        source = "notice"
        detail = "Using the test date you entered. Verify with MVA."
    elif last is not None:
        due = add_months(last, rules.veip_cycle_months)
        source = "cycle"
        detail = f"Last test plus {rules.veip_cycle_months} months from the rules file."
    elif first is not None and as_of < first:
        due = first
        source = "new_vehicle_anchor"
        detail = (
            f"Estimated first test is {rules.new_exempt_months} months from "
            f"{rules.new_anchor.replace('_', ' ')}. Verify with MVA."
        )
    elif first is not None:
        due = first
        source = "new_vehicle_anchor"
        detail = "The estimated first-test date from the rules file is already past. Verify with MVA."
    elif rules.apply_used_purchase_notice_as_due_date and vehicle.get("title_date") is not None:
        due = add_months(vehicle["title_date"], rules.used_purchase_notice_months)
        source = "used_purchase_notice"
        detail = (
            f"Rules file is set to treat a used-purchase notice at "
            f"{rules.used_purchase_notice_months} months as the due date. Verify with MVA."
        )
    else:
        return VeipAssessment(
            required=True,
            exempt=False,
            exemption_id=None,
            due=None,
            due_source="missing",
            notice=None,
            late_fee_usd=0,
            first_test=first,
            detail="Enter the due date from your MVA notice. The rules file will not invent one.",
        )
    in_new_window = first is not None and as_of < first and override is None and last is None
    return VeipAssessment(
        required=True,
        exempt=in_new_window,
        exemption_id="new_vehicle_window" if in_new_window else None,
        due=due,
        due_source=source,
        notice=veip_notice_window(due, rules),
        late_fee_usd=veip_late_fee_usd(due, as_of, rules),
        first_test=first,
        detail=detail,
    )


@dataclass(frozen=True)
class RegistrationAssessment:
    expiration: date | None
    planning_due: date | None
    month_end: date | None
    period_years: int | None
    early_renew_opens: date | None
    published_notice_on: date | None
    mail_deadline: date | None
    flag_email_on: date | None
    next_after_renewal: date | None
    detail: str


def registration_planning_due(card_date: date, rules: MarylandRules) -> date:
    if rules.planning_deadline == "last_day_of_month_on_card":
        return month_end(card_date)
    return card_date


def assess_registration(
    card_date: date | None,
    period_years: int | None,
    rules: MarylandRules,
) -> RegistrationAssessment:
    if card_date is None:
        return RegistrationAssessment(
            expiration=None,
            planning_due=None,
            month_end=None,
            period_years=period_years,
            early_renew_opens=None,
            published_notice_on=None,
            mail_deadline=None,
            flag_email_on=None,
            next_after_renewal=None,
            detail="Enter the expiration date printed on the registration card.",
        )
    planning = registration_planning_due(card_date, rules)
    notice_on = None
    if rules.registration_notice_lead_days is not None:
        notice_on = card_date - timedelta(days=rules.registration_notice_lead_days)
    nxt = None
    if period_years is not None:
        if period_years not in rules.registration_periods_allowed():
            raise ValueError(
                f"{period_years}-year registration is not listed in the rules file"
            )
        nxt = add_years(card_date, period_years)
    return RegistrationAssessment(
        expiration=card_date,
        planning_due=planning,
        month_end=month_end(card_date),
        period_years=period_years,
        early_renew_opens=card_date - timedelta(days=rules.early_renew_days),
        published_notice_on=notice_on,
        mail_deadline=card_date - timedelta(days=rules.mail_must_arrive_days),
        flag_email_on=card_date - timedelta(days=rules.flag_email_days),
        next_after_renewal=nxt,
        detail=rules.registration_notice_statement,
    )


def alarm_wall_time(due_local: datetime, days: int) -> datetime:
    """Same clock time, `days` calendar days earlier, in `due_local`'s zone.

    Subtracting `days * 24` hours instead of calendar days moves the clock
    across a daylight-saving transition. This does not.
    """
    if due_local.tzinfo is None:
        raise ValueError("due_local needs a time zone")
    zone = due_local.tzinfo
    local = due_local.astimezone(zone)
    shifted = local.date() - timedelta(days=days)
    return datetime(shifted.year, shifted.month, shifted.day, local.hour, local.minute, tzinfo=zone)
