import time_machine

from app.enums import TriggerType
from app.parsing.relative_schedule import try_parse_once_schedule
from tests.constants import FROZEN_TIME


@time_machine.travel(FROZEN_TIME, tick=False)
def test_try_parse_once_in_one_hour():
    spec = try_parse_once_schedule("in one hour", now=FROZEN_TIME, timezone="UTC")

    assert spec is not None
    assert spec.type == TriggerType.ONCE
    assert spec.run_at.isoformat() == "2026-05-24T09:00:00+00:00"


@time_machine.travel(FROZEN_TIME, tick=False)
def test_try_parse_once_tomorrow_morning():
    spec = try_parse_once_schedule("tomorrow morning", now=FROZEN_TIME, timezone="UTC")

    assert spec is not None
    assert spec.run_at.isoformat() == "2026-05-25T09:00:00+00:00"


@time_machine.travel(FROZEN_TIME, tick=False)
def test_try_parse_once_tomorrow_at_time():
    spec = try_parse_once_schedule(
        "Tomorrow at 8:15 AM",
        now=FROZEN_TIME,
        timezone="UTC",
    )

    assert spec is not None
    assert spec.run_at.isoformat() == "2026-05-25T08:15:00+00:00"


@time_machine.travel(FROZEN_TIME, tick=False)
def test_try_parse_once_next_friday_at_5pm():
    spec = try_parse_once_schedule(
        "Next Friday at 5pm",
        now=FROZEN_TIME,
        timezone="UTC",
    )

    assert spec is not None
    assert spec.run_at.isoformat() == "2026-05-29T17:00:00+00:00"


@time_machine.travel(FROZEN_TIME, tick=False)
def test_try_parse_once_skips_recurring_phrases():
    assert (
        try_parse_once_schedule("every day at 9am", now=FROZEN_TIME, timezone="UTC")
        is None
    )
    assert (
        try_parse_once_schedule("every Tuesday at 9am", now=FROZEN_TIME, timezone="UTC")
        is None
    )


@time_machine.travel(FROZEN_TIME, tick=False)
def test_try_parse_once_in_30_minutes():
    spec = try_parse_once_schedule("in 30 minutes", now=FROZEN_TIME, timezone="UTC")

    assert spec is not None
    assert spec.run_at.isoformat() == "2026-05-24T08:30:00+00:00"
