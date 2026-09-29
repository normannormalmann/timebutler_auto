from __future__ import annotations

import random
from datetime import date, time, timedelta, timezone

import pytest

import tb_schedule as ts

TZ = timezone(timedelta(hours=2))
WEDNESDAY = date(2026, 9, 30)
SATURDAY = date(2026, 10, 3)


@pytest.mark.parametrize("seed", range(200))
def test_build_plan_respects_all_windows(seed):
    plan = ts.build_plan(WEDNESDAY, ts.ScheduleConfig(), TZ, random.Random(seed))

    assert time(9, 0) <= plan.start_at.time() <= time(9, 30)
    assert time(12, 0) <= plan.pause_at.time() <= time(13, 0)
    assert plan.resume_at - plan.pause_at == timedelta(minutes=30)
    presence = plan.stop_at - plan.start_at
    assert timedelta(hours=7, minutes=30) <= presence <= timedelta(hours=9)
    assert plan.pause_at - plan.start_at <= ts.MAX_WORK_BEFORE_BREAK
    assert plan.start_at < plan.pause_at < plan.resume_at < plan.stop_at


def test_build_plan_uses_full_minutes_and_timezone():
    plan = ts.build_plan(WEDNESDAY, ts.ScheduleConfig(), TZ, random.Random(1))
    for moment in (plan.start_at, plan.pause_at, plan.resume_at, plan.stop_at):
        assert moment.second == 0 and moment.microsecond == 0
        assert moment.utcoffset() == timedelta(hours=2)


def test_to_dict_reports_iso_times_and_durations():
    plan = ts.DayPlan(
        WEDNESDAY,
        start_at=ts.datetime(2026, 9, 30, 9, 10, tzinfo=TZ),
        pause_at=ts.datetime(2026, 9, 30, 12, 15, tzinfo=TZ),
        resume_at=ts.datetime(2026, 9, 30, 12, 45, tzinfo=TZ),
        stop_at=ts.datetime(2026, 9, 30, 17, 40, tzinfo=TZ),
    )
    data = plan.to_dict()
    assert data["work"] is True
    assert data["start_at"] == "2026-09-30T09:10:00+02:00"
    assert data["presence_minutes"] == 510
    assert data["break_minutes"] == 30


def test_non_work_reason_weekend_skip_and_holiday():
    config = ts.ScheduleConfig(skip_dates=frozenset({WEDNESDAY}))
    assert ts.non_work_reason(SATURDAY, config) == "no workday"
    assert ts.non_work_reason(WEDNESDAY, config) == "skip date"

    thursday = WEDNESDAY + timedelta(days=1)
    assert ts.non_work_reason(thursday, config) is None
    lookup = lambda day: "Feiertag" if day == thursday else None  # noqa: E731
    assert ts.non_work_reason(thursday, config, lookup) == "public holiday: Feiertag"


def test_parse_skip_dates_supports_ranges_and_comments():
    days = ts.parse_skip_dates(
        ["# Urlaub", "2026-10-05..2026-10-07", "", "2026-12-24  # Heiligabend"]
    )
    assert days == {
        date(2026, 10, 5),
        date(2026, 10, 6),
        date(2026, 10, 7),
        date(2026, 12, 24),
    }


def test_parse_skip_dates_rejects_reversed_range():
    with pytest.raises(ValueError):
        ts.parse_skip_dates(["2026-10-07..2026-10-05"])


def test_load_skip_dates_missing_file_is_empty(tmp_path):
    assert ts.load_skip_dates(tmp_path / "nope.txt") == frozenset()


def test_config_from_env_defaults():
    assert ts.config_from_env({}) == ts.ScheduleConfig()


def test_config_from_env_parses_overrides():
    config = ts.config_from_env(
        {
            "TB_START_WINDOW": "08:00-08:15",
            "TB_SHIFT_HOURS": "8-8,5",
            "TB_BREAK_MINUTES": "45",
            "TB_BREAK_WINDOW": "11:30-12:30",
            "TB_WORKDAYS": "1,2,3,4",
        }
    )
    assert config.start_window == (time(8, 0), time(8, 15))
    assert config.shift_minutes == (480, 510)
    assert config.break_minutes == 45
    assert config.break_window == (time(11, 30), time(12, 30))
    assert config.workdays == {1, 2, 3, 4}


@pytest.mark.parametrize(
    "env",
    [
        {"TB_BREAK_WINDOW": "14:00-16:00"},  # break later than 6 h after start
        {"TB_BREAK_WINDOW": "09:00-10:00"},  # break could begin before start
        {"TB_SHIFT_HOURS": "3-4"},  # shift ends before the break is over
        {"TB_START_WINDOW": "09:30-09:00"},  # reversed range
    ],
)
def test_config_from_env_rejects_invalid_schedules(env):
    with pytest.raises(ValueError):
        ts.config_from_env(env)


def test_plan_for_day_is_stable_across_calls(tmp_path):
    store = ts.PlanStore(tmp_path / "plan.json")
    config = ts.ScheduleConfig()
    first = ts.plan_for_day(WEDNESDAY, config, TZ, store, rng=random.Random(1))
    second = ts.plan_for_day(WEDNESDAY, config, TZ, store, rng=random.Random(99))
    assert first == second


def test_plan_for_day_regenerates_for_a_new_day(tmp_path):
    store = ts.PlanStore(tmp_path / "plan.json")
    config = ts.ScheduleConfig()
    ts.plan_for_day(WEDNESDAY, config, TZ, store, rng=random.Random(1))
    thursday = WEDNESDAY + timedelta(days=1)
    plan = ts.plan_for_day(thursday, config, TZ, store, rng=random.Random(1))
    assert plan["date"] == thursday.isoformat()


def test_plan_for_other_day_keeps_todays_plan(tmp_path):
    store = ts.PlanStore(tmp_path / "plan.json")
    config = ts.ScheduleConfig()
    today = ts.plan_for_day(WEDNESDAY, config, TZ, store, rng=random.Random(1))
    ts.plan_for_day(WEDNESDAY + timedelta(days=1), config, TZ, store, rng=random.Random(2))
    assert ts.plan_for_day(WEDNESDAY, config, TZ, store, rng=random.Random(3)) == today


def test_plan_store_prunes_old_days(tmp_path):
    store = ts.PlanStore(tmp_path / "plan.json")
    for offset in range(ts.PlanStore.KEEP_DAYS + 5):
        day = WEDNESDAY + timedelta(days=offset)
        store.save({"date": day.isoformat()})
    assert store.load(WEDNESDAY) is None
    assert store.load(WEDNESDAY + timedelta(days=ts.PlanStore.KEEP_DAYS + 4)) is not None


def test_plan_for_day_skip_date_wins_over_stored_plan(tmp_path):
    store = ts.PlanStore(tmp_path / "plan.json")
    ts.plan_for_day(WEDNESDAY, ts.ScheduleConfig(), TZ, store, rng=random.Random(1))
    skipping = ts.ScheduleConfig(skip_dates=frozenset({WEDNESDAY}))
    plan = ts.plan_for_day(WEDNESDAY, skipping, TZ, store)
    assert plan == {"date": "2026-09-30", "work": False, "reason": "skip date"}


def test_plan_store_ignores_corrupt_file(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text("{broken", encoding="utf-8")
    assert ts.PlanStore(path).load(WEDNESDAY) is None
