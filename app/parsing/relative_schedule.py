import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.schemas.tasks import OnceTrigger

RECURRING_PATTERN = re.compile(
    r"\b("
    r"every|each|daily|weekly|hourly|biweekly|fortnightly|"
    r"weekdays?|weekends?"
    r")\b",
    re.IGNORECASE,
)

WEEKDAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

WORD_NUMBERS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

TIME_OF_DAY: dict[str, tuple[int, int]] = {
    "morning": (9, 0),
    "noon": (12, 0),
    "afternoon": (14, 0),
    "evening": (18, 0),
    "midnight": (0, 0),
}

DEFAULT_HOUR_MINUTE = (9, 0)

AT_TIME_PATTERN = re.compile(
    r"(?:\bat\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
    re.IGNORECASE,
)

IN_DURATION_PATTERN = re.compile(
    r"\bin\s+([a-z]+|\d+)\s+(second|seconds|minute|minutes|hour|hours|day|days)\b",
    re.IGNORECASE,
)

TOMORROW_PATTERN = re.compile(r"\btomorrow\b", re.IGNORECASE)

NEXT_WEEKDAY_PATTERN = re.compile(
    r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)


def _localize(now: datetime, timezone: str) -> datetime:
    tz = ZoneInfo(timezone)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def _parse_at_time(text: str) -> tuple[int, int] | None:
    match = AT_TIME_PATTERN.search(text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3).lower()
    match meridiem:
        case "pm" if hour != 12:
            hour += 12
        case "am" if hour == 12:
            hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _parse_time_of_day(text: str) -> tuple[int, int] | None:
    lower = text.lower()
    for keyword, hour_minute in TIME_OF_DAY.items():
        if re.search(rf"\b{keyword}\b", lower):
            return hour_minute
    return _parse_at_time(text)


def _apply_time(base: datetime, hour_minute: tuple[int, int]) -> datetime:
    hour, minute = hour_minute
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def try_parse_once_schedule(text: str, *, now: datetime, timezone: str) -> OnceTrigger | None:
    if RECURRING_PATTERN.search(text):
        return None

    localized = _localize(now, timezone)

    in_match = IN_DURATION_PATTERN.search(text)
    if in_match:
        amount_raw = in_match.group(1).lower()
        unit = in_match.group(2).lower()
        amount = int(amount_raw) if amount_raw.isdigit() else WORD_NUMBERS.get(amount_raw)
        if amount is None:
            return None
        match unit:
            case "second" | "seconds":
                delta = timedelta(seconds=amount)
            case "minute" | "minutes":
                delta = timedelta(minutes=amount)
            case "hour" | "hours":
                delta = timedelta(hours=amount)
            case "day" | "days":
                delta = timedelta(days=amount)
            case _:
                return None
        return OnceTrigger(run_at=localized + delta)

    if TOMORROW_PATTERN.search(text):
        target = localized + timedelta(days=1)
        hour_minute = _parse_time_of_day(text) or DEFAULT_HOUR_MINUTE
        return OnceTrigger(run_at=_apply_time(target, hour_minute))

    next_weekday_match = NEXT_WEEKDAY_PATTERN.search(text)
    if next_weekday_match:
        weekday = WEEKDAY_NAMES[next_weekday_match.group(1).lower()]
        days_ahead = weekday - localized.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        target = localized + timedelta(days=days_ahead)
        hour_minute = _parse_time_of_day(text) or DEFAULT_HOUR_MINUTE
        return OnceTrigger(run_at=_apply_time(target, hour_minute))

    return None
