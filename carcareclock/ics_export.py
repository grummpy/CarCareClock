"""ICS export with a 7-day display alarm in America/New_York.

Events are timed at 9:00 local, not floating UTC, and the alarm is a calendar
duration (-P7D) rather than 168 hours. That keeps the reminder on the same
clock time across the daylight-saving transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Alarm, Calendar, Event, Timezone

from carcareclock.schedule import NEW_YORK, alarm_wall_time

ALARM_DAYS = 7
EVENT_HOUR = 9


@dataclass(frozen=True)
class CalendarItem:
    uid: str
    summary: str
    description: str
    due: date


def event_start(due: date, zone: ZoneInfo = NEW_YORK) -> datetime:
    return datetime(due.year, due.month, due.day, EVENT_HOUR, 0, tzinfo=zone)


def build_calendar(items: list[CalendarItem], alarm_days: int = ALARM_DAYS) -> bytes:
    if alarm_days < 0:
        raise ValueError("alarm_days must be zero or more")
    cal = Calendar()
    cal.add("prodid", "-//CarCareClock//carcareclock//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "CarCareClock")
    cal.add("x-wr-timezone", "America/New_York")
    zone = Timezone.from_tzid(
        "America/New_York",
        first_date=date(2020, 1, 1),
        last_date=date(2038, 1, 1),
    )
    cal.add_component(zone)
    stamp = datetime.now(tz=NEW_YORK)
    for item in items:
        event = Event()
        start = event_start(item.due)
        event.add("uid", item.uid)
        event.add("summary", item.summary)
        event.add("description", item.description)
        event.add("dtstart", start)
        event.add("dtend", start + timedelta(minutes=30))
        event.add("dtstamp", stamp)
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", item.summary)
        alarm.add("trigger", timedelta(days=-alarm_days))
        event.add_component(alarm)
        cal.add_component(event)
    return cal.to_ical()


def alarm_for(due: date, alarm_days: int = ALARM_DAYS) -> datetime:
    """Wall-clock time of the display alarm. Used to check the DST edge."""
    return alarm_wall_time(event_start(due), alarm_days)
