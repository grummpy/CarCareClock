"""Whichever-comes-first, mileage projection, and the 7-day reminder window."""

from datetime import UTC, date, datetime, timedelta

from carcareclock.schedule import (
    NEW_YORK,
    alarm_wall_time,
    in_reminder_window,
    miles_per_day,
    project_mileage_date,
    reminder_status,
    whichever_comes_first,
)


def test_months_comes_first():
    readings = [(date(2026, 1, 1), 10000), (date(2026, 1, 11), 10100)]
    result = whichever_comes_first(
        last_date=date(2026, 1, 1),
        last_miles=10000,
        months_interval=3,
        miles_interval=10000,
        readings=readings,
        today=date(2026, 1, 11),
    )
    assert result.due == date(2026, 4, 1)
    assert result.reason == "months"


def test_mileage_comes_first():
    readings = [(date(2026, 1, 1), 1000), (date(2026, 1, 11), 1100)]
    result = whichever_comes_first(
        last_date=date(2026, 1, 1),
        last_miles=1000,
        months_interval=24,
        miles_interval=150,
        readings=readings,
        today=date(2026, 1, 11),
    )
    # 10 miles/day, 50 miles left, anchored on the latest reading.
    assert miles_per_day(readings) == 10
    assert result.due == date(2026, 1, 16)
    assert result.reason == "miles"


def test_only_one_interval_and_a_tie():
    months_only = whichever_comes_first(
        last_date=date(2026, 3, 15),
        last_miles=None,
        months_interval=6,
        miles_interval=None,
        readings=[],
        today=date(2026, 3, 15),
    )
    assert months_only.due == date(2026, 9, 15)
    assert months_only.reason == "months"

    readings = [(date(2026, 1, 1), 0), (date(2026, 1, 11), 100)]
    miles_only = whichever_comes_first(
        last_date=None,
        last_miles=0,
        months_interval=None,
        miles_interval=150,
        readings=readings,
        today=date(2026, 1, 11),
    )
    assert miles_only.due == date(2026, 1, 16)
    assert miles_only.reason == "miles"

    tie = whichever_comes_first(
        last_date=date(2026, 1, 1),
        last_miles=1000,
        months_interval=1,
        miles_interval=310,
        readings=[(date(2026, 1, 1), 1000), (date(2026, 1, 11), 1100)],
        today=date(2026, 1, 11),
    )
    # rate 10/day from Jan 1 to Jan 11. remaining = 1000+310-1100 = 210. days = 21.
    # anchor Jan 11 + 21 = Feb 1. months: Feb 1. Tie.
    assert tie.due == date(2026, 2, 1)
    assert tie.reason == "both"


def test_already_past_the_mileage_target():
    result = whichever_comes_first(
        last_date=date(2026, 6, 1),
        last_miles=1000,
        months_interval=12,
        miles_interval=100,
        readings=[(date(2026, 1, 1), 1000), (date(2026, 8, 1), 1200)],
        today=date(2026, 8, 1),
    )
    assert result.due == date(2026, 8, 1)
    assert result.reason == "miles"


def test_mileage_without_a_rate_needs_readings():
    result = whichever_comes_first(
        last_date=None,
        last_miles=1000,
        months_interval=None,
        miles_interval=500,
        readings=[(date(2026, 5, 1), 1100)],
        today=date(2026, 5, 1),
    )
    assert result.due is None
    assert result.needs_readings


def test_projection_uses_calendar_days_across_the_dst_change():
    # US clocks spring forward on 2026-03-08. One calendar day is still one day.
    anchor = date(2026, 3, 7)
    assert project_mileage_date(anchor, 10, 10) == date(2026, 3, 8)
    assert project_mileage_date(anchor, 30, 10) == date(2026, 3, 10)
    readings = [(date(2026, 3, 7), 1000), (date(2026, 3, 9), 1040)]
    assert (readings[1][0] - readings[0][0]).days == 2
    assert miles_per_day(readings) == 20


def test_seven_day_window_includes_overdue_and_excludes_day_eight():
    today = date(2026, 6, 1)
    assert in_reminder_window(today - timedelta(days=3), today, 7)
    assert in_reminder_window(today, today, 7)
    assert in_reminder_window(today + timedelta(days=7), today, 7)
    assert not in_reminder_window(today + timedelta(days=8), today, 7)
    assert reminder_status(today + timedelta(days=7), today, 7) == "due_soon"
    assert reminder_status(today + timedelta(days=8), today, 7) == "upcoming"
    assert reminder_status(today - timedelta(days=1), today, 7) == "overdue"
    # The window length comes from the caller, not a hardcoded 7.
    assert not in_reminder_window(today + timedelta(days=4), today, 3)
    assert in_reminder_window(today + timedelta(days=3), today, 3)


def test_alarm_wall_time_does_not_shift_across_dst():
    spring = datetime(2026, 3, 9, 9, 0, tzinfo=NEW_YORK)
    fall = datetime(2026, 11, 2, 9, 0, tzinfo=NEW_YORK)
    assert spring.utcoffset() != datetime(2026, 3, 7, 9, 0, tzinfo=NEW_YORK).utcoffset()
    assert fall.utcoffset() != datetime(2026, 10, 31, 9, 0, tzinfo=NEW_YORK).utcoffset()

    spring_alarm = alarm_wall_time(spring, 7)
    fall_alarm = alarm_wall_time(fall, 7)
    assert spring_alarm == datetime(2026, 3, 2, 9, 0, tzinfo=NEW_YORK)
    assert fall_alarm == datetime(2026, 10, 26, 9, 0, tzinfo=NEW_YORK)

    spring_absolute = (spring.astimezone(UTC) - timedelta(days=7)).astimezone(NEW_YORK)
    fall_absolute = (fall.astimezone(UTC) - timedelta(days=7)).astimezone(NEW_YORK)
    assert spring_absolute.hour == 8
    assert fall_absolute.hour == 10
