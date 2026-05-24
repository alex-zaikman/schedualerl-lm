from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_TRIGGER_PARSE_PROMPT_PATH = Path(__file__).resolve().parent / "trigger_parse.txt"

CURRENT_ISO_DATETIME_PLACEHOLDER = "[INJECT_CURRENT_ISO_DATETIME]"
DEFAULT_TIMEZONE_PLACEHOLDER = "[INJECT_DEFAULT_TIMEZONE]"
CURRENT_DATE_PLACEHOLDER = "[INJECT_CURRENT_DATE]"
TOMORROW_MORNING_ISO_PLACEHOLDER = "[INJECT_TOMORROW_MORNING_ISO]"
TOMORROW_0815_ISO_PLACEHOLDER = "[INJECT_TOMORROW_0815_ISO]"
NEXT_FRIDAY_5PM_ISO_PLACEHOLDER = "[INJECT_NEXT_FRIDAY_5PM_ISO]"
ONE_HOUR_LATER_ISO_PLACEHOLDER = "[INJECT_ONE_HOUR_LATER_ISO]"
NEXT_TUESDAY_9AM_ISO_PLACEHOLDER = "[INJECT_NEXT_TUESDAY_9AM_ISO]"


class PromptLoadError(Exception):
    pass


def load_prompt(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise PromptLoadError(f"Failed to read prompt file {path}: {exc}") from exc

    if not content:
        raise PromptLoadError(f"Prompt file {path} is empty")

    return content


def _localize_now(now: datetime, timezone: str) -> datetime:
    tz = ZoneInfo(timezone)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def _next_weekday(from_dt: datetime, weekday: int) -> datetime:
    days_ahead = weekday - from_dt.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return from_dt + timedelta(days=days_ahead)


def build_trigger_parse_placeholders(*, now: datetime, timezone: str) -> dict[str, str]:
    localized = _localize_now(now, timezone)
    tomorrow = localized + timedelta(days=1)
    next_friday = _next_weekday(localized, 4)

    return {
        CURRENT_ISO_DATETIME_PLACEHOLDER: localized.isoformat(),
        DEFAULT_TIMEZONE_PLACEHOLDER: timezone,
        CURRENT_DATE_PLACEHOLDER: localized.date().isoformat(),
        TOMORROW_MORNING_ISO_PLACEHOLDER: tomorrow.replace(
            hour=9, minute=0, second=0, microsecond=0
        ).isoformat(),
        TOMORROW_0815_ISO_PLACEHOLDER: tomorrow.replace(
            hour=8, minute=15, second=0, microsecond=0
        ).isoformat(),
        NEXT_FRIDAY_5PM_ISO_PLACEHOLDER: next_friday.replace(
            hour=17, minute=0, second=0, microsecond=0
        ).isoformat(),
        ONE_HOUR_LATER_ISO_PLACEHOLDER: (localized + timedelta(hours=1)).isoformat(),
        NEXT_TUESDAY_9AM_ISO_PLACEHOLDER: _next_weekday(localized, 1).replace(
            hour=9, minute=0, second=0, microsecond=0
        ).isoformat(),
    }


def render_trigger_parse_prompt(content: str, *, now: datetime, timezone: str) -> str:
    rendered = content
    for placeholder, value in build_trigger_parse_placeholders(
        now=now,
        timezone=timezone,
    ).items():
        rendered = rendered.replace(placeholder, value)
    if "[INJECT_" in rendered:
        raise PromptLoadError("Unreplaced placeholders remain in trigger parse prompt")
    return rendered
