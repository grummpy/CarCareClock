"""The calendar file parses, names America/New_York, and keeps a 7-day alarm across DST."""

from datetime import date, datetime, timedelta

from icalendar import Calendar

from carcareclock.ics_export import CalendarItem, alarm_for, build_calendar
from carcareclock.schedule import NEW_YORK


def _item(due: date, name: str) -> CalendarItem:
    return CalendarItem(
        uid=f"test-{name}@local",
        summary=f"{name} reminder",
        description="Verify with MVA.",
        due=due,
    )


def test_ics_parses_with_new_york_and_a_seven_day_alarm():
    payload = build_calendar(
        [_item(date(2026, 6, 5), "emissions"), _item(date(2026, 6, 21), "registration")],
        alarm_days=7,
    )
    calendar = Calendar.from_ical(payload)
    zones = [component for component in calendar.walk("VTIMEZONE")]
    assert zones
    assert str(zones[0]["tzid"]) == "America/New_York"
    text = payload.decode()
    assert "America/New_York" in text
    assert "TRIGGER:-P7D" in text

    events = list(calendar.walk("VEVENT"))
    assert len(events) == 2
    start = events[0].decoded("dtstart")
    local = start.astimezone(NEW_YORK)
    assert local.date() == date(2026, 6, 5)
    assert local.hour == 9
    alarms = list(events[0].walk("VALARM"))
    assert alarms[0].decoded("trigger") == timedelta(days=-7)
    assert alarm_for(date(2026, 6, 5), 7) == datetime(2026, 5, 29, 9, 0, tzinfo=NEW_YORK)


def test_dst_edge_alarm_stays_at_nine_local():
    spring_due = date(2026, 3, 9)
    fall_due = date(2026, 11, 2)
    payload = build_calendar([_item(spring_due, "spring"), _item(fall_due, "fall")], alarm_days=7)
    calendar = Calendar.from_ical(payload)
    by_day = {}
    for event in calendar.walk("VEVENT"):
        local = event.decoded("dtstart").astimezone(NEW_YORK)
        by_day[local.date()] = event
        assert local.hour == 9
        assert list(event.walk("VALARM"))[0].decoded("trigger") == timedelta(days=-7)

    assert alarm_for(spring_due) == datetime(2026, 3, 2, 9, 0, tzinfo=NEW_YORK)
    assert alarm_for(fall_due) == datetime(2026, 10, 26, 9, 0, tzinfo=NEW_YORK)
    assert by_day[spring_due].decoded("dtstart").astimezone(NEW_YORK).hour == 9
    assert by_day[fall_due].decoded("dtstart").astimezone(NEW_YORK).hour == 9
