"""
Daily work plan for the n8n-driven time clock.

A plan fixes, per working day, when to start, pause, resume and stop the
Timebutler time recorder:

- start at a random minute inside the start window (default 09:00-09:30)
- a break of fixed length (default 30 min) starting inside the break window
- stop 7.5 to 9 hours after the start (gross presence time, break included)

German working-time law (ArbZG) requires a break after at most six hours of
work, so plans whose break would start later than that are rejected.

Plans are persisted per day, so repeated /plan calls (n8n retries, manual
re-runs) always return the same times.
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import Path
from typing import Callable, FrozenSet, Iterable, Mapping, Optional, Tuple

MAX_WORK_BEFORE_BREAK = timedelta(hours=6)

HolidayLookup = Callable[[date], Optional[str]]


@dataclass(frozen=True)
class ScheduleConfig:
    start_window: Tuple[time, time] = (time(9, 0), time(9, 30))
    shift_minutes: Tuple[int, int] = (450, 540)  # 7.5 h .. 9 h, break included
    break_minutes: int = 30
    break_window: Tuple[time, time] = (time(12, 0), time(13, 0))
    workdays: FrozenSet[int] = frozenset({1, 2, 3, 4, 5})  # ISO weekdays, Mon=1
    skip_dates: FrozenSet[date] = field(default_factory=frozenset)


@dataclass(frozen=True)
class DayPlan:
    day: date
    start_at: datetime
    pause_at: datetime
    resume_at: datetime
    stop_at: datetime

    def to_dict(self) -> dict:
        return {
            "date": self.day.isoformat(),
            "work": True,
            "start_at": self.start_at.isoformat(),
            "pause_at": self.pause_at.isoformat(),
            "resume_at": self.resume_at.isoformat(),
            "stop_at": self.stop_at.isoformat(),
            "presence_minutes": int((self.stop_at - self.start_at).total_seconds() // 60),
            "break_minutes": int((self.resume_at - self.pause_at).total_seconds() // 60),
        }


def _parse_time(value: str) -> time:
    hours, minutes = value.strip().split(":")
    return time(int(hours), int(minutes))


def _parse_time_range(value: str) -> Tuple[time, time]:
    start, end = (_parse_time(part) for part in value.split("-"))
    if end < start:
        raise ValueError(f"Time range ends before it starts: {value!r}")
    return start, end


def _parse_hours_range(value: str) -> Tuple[int, int]:
    low, high = (round(float(part.strip().replace(",", ".")) * 60) for part in value.split("-"))
    if high < low:
        raise ValueError(f"Hour range ends before it starts: {value!r}")
    return low, high


def parse_skip_dates(lines: Iterable[str]) -> FrozenSet[date]:
    """Parses one date (2026-12-24) or range (2026-10-05..2026-10-09) per line.

    Blank lines and lines starting with '#' are ignored.
    """
    days = set()
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ".." in line:
            first, last = (date.fromisoformat(part.strip()) for part in line.split(".."))
            if last < first:
                raise ValueError(f"Date range ends before it starts: {line!r}")
            days.update(first + timedelta(days=i) for i in range((last - first).days + 1))
        else:
            days.add(date.fromisoformat(line))
    return frozenset(days)


def load_skip_dates(path: Path) -> FrozenSet[date]:
    if not path.exists():
        return frozenset()
    return parse_skip_dates(path.read_text(encoding="utf-8-sig").splitlines())


def config_from_env(env: Mapping[str, str], skip_dates: FrozenSet[date] = frozenset()) -> ScheduleConfig:
    """Builds the schedule from TB_* environment variables (all optional)."""
    defaults = ScheduleConfig()
    workdays = env.get("TB_WORKDAYS")
    config = ScheduleConfig(
        start_window=_parse_time_range(env["TB_START_WINDOW"]) if env.get("TB_START_WINDOW") else defaults.start_window,
        shift_minutes=_parse_hours_range(env["TB_SHIFT_HOURS"]) if env.get("TB_SHIFT_HOURS") else defaults.shift_minutes,
        break_minutes=int(env.get("TB_BREAK_MINUTES") or defaults.break_minutes),
        break_window=_parse_time_range(env["TB_BREAK_WINDOW"]) if env.get("TB_BREAK_WINDOW") else defaults.break_window,
        workdays=frozenset(int(d) for d in workdays.split(",")) if workdays else defaults.workdays,
        skip_dates=skip_dates,
    )
    validate_config(config)
    return config


def validate_config(config: ScheduleConfig) -> None:
    """Rejects configurations that could produce an illegal or impossible day."""
    anchor = date(2000, 1, 3)
    latest_start = datetime.combine(anchor, config.start_window[1])
    earliest_start = datetime.combine(anchor, config.start_window[0])
    latest_break = datetime.combine(anchor, config.break_window[1])
    earliest_break = datetime.combine(anchor, config.break_window[0])
    if config.break_minutes < 0:
        raise ValueError("TB_BREAK_MINUTES must not be negative.")
    if earliest_break <= latest_start:
        raise ValueError("The break window must begin after the latest possible start.")
    if latest_break - earliest_start > MAX_WORK_BEFORE_BREAK:
        raise ValueError("The break could start more than 6 hours after the start (ArbZG).")
    earliest_stop = earliest_start + timedelta(minutes=config.shift_minutes[0])
    if latest_break + timedelta(minutes=config.break_minutes) >= earliest_stop:
        raise ValueError("The shortest shift would end before the break is over.")


def non_work_reason(
    day: date, config: ScheduleConfig, holiday_lookup: Optional[HolidayLookup] = None
) -> Optional[str]:
    """Returns why `day` is not a working day, or None if it is one."""
    if day.isoweekday() not in config.workdays:
        return "no workday"
    if day in config.skip_dates:
        return "skip date"
    if holiday_lookup is not None:
        holiday = holiday_lookup(day)
        if holiday:
            return f"public holiday: {holiday}"
    return None


def _random_minute(rng: random.Random, earliest: datetime, latest: datetime) -> datetime:
    span = int((latest - earliest).total_seconds() // 60)
    return earliest + timedelta(minutes=rng.randint(0, max(span, 0)))


def build_plan(day: date, config: ScheduleConfig, tz: tzinfo, rng: random.Random) -> DayPlan:
    start_at = _random_minute(
        rng,
        datetime.combine(day, config.start_window[0], tzinfo=tz),
        datetime.combine(day, config.start_window[1], tzinfo=tz),
    )
    pause_at = _random_minute(
        rng,
        datetime.combine(day, config.break_window[0], tzinfo=tz),
        min(datetime.combine(day, config.break_window[1], tzinfo=tz), start_at + MAX_WORK_BEFORE_BREAK),
    )
    resume_at = pause_at + timedelta(minutes=config.break_minutes)
    stop_at = start_at + timedelta(minutes=rng.randint(*config.shift_minutes))
    return DayPlan(day, start_at, pause_at, resume_at, stop_at)


class PlanStore:
    """Persists plans per day so they stay stable across calls."""

    KEEP_DAYS = 14

    def __init__(self, path: Path):
        self.path = path

    def _read_all(self) -> dict:
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return stored if isinstance(stored, dict) else {}

    def load(self, day: date) -> Optional[dict]:
        return self._read_all().get(day.isoformat())

    def save(self, plan: dict) -> None:
        plans = {**self._read_all(), plan["date"]: plan}
        newest = sorted(plans)[-self.KEEP_DAYS:]
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        tmp_path.write_text(json.dumps({d: plans[d] for d in newest}, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.path)


def plan_for_day(
    day: date,
    config: ScheduleConfig,
    tz: tzinfo,
    store: PlanStore,
    holiday_lookup: Optional[HolidayLookup] = None,
    rng: Optional[random.Random] = None,
) -> dict:
    """Returns the (persisted) plan for `day` as a JSON-ready dict."""
    reason = non_work_reason(day, config, holiday_lookup)
    if reason is not None:
        return {"date": day.isoformat(), "work": False, "reason": reason}

    stored = store.load(day)
    if stored is not None:
        return stored

    plan = build_plan(day, config, tz, rng or random.SystemRandom()).to_dict()
    store.save(plan)
    return plan
