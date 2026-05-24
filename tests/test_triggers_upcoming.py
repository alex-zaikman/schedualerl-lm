from datetime import datetime, timedelta, timezone
from uuid import uuid4

import time_machine

from app.db.models.scheduled_task import ScheduledTask
from app.enums import TriggerType
from app.scheduler.triggers import compute_upcoming_run_times
from tests.constants import FROZEN_TIME, TEST_USER_ID


def _task(trigger_type: TriggerType, trigger_config: dict) -> ScheduledTask:
    return ScheduledTask(
        id=uuid4(),
        user_id=TEST_USER_ID,
        webhook_url="https://example.com/hook",
        parameters={},
        trigger_type=trigger_type,
        trigger_config=trigger_config,
        is_active=True,
    )


@time_machine.travel(FROZEN_TIME, tick=False)
def test_upcoming_cron_returns_n_times():
    task = _task(
        TriggerType.CRON,
        {"expression": "0 9 * * *", "timezone": "UTC"},
    )
    times = compute_upcoming_run_times(task, count=3)
    assert times == [
        datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 5, 26, 9, 0, tzinfo=timezone.utc),
    ]


@time_machine.travel(FROZEN_TIME, tick=False)
def test_upcoming_interval_spaced():
    task = _task(TriggerType.INTERVAL, {"seconds": 300})
    times = compute_upcoming_run_times(task, count=3)
    assert times == [
        FROZEN_TIME,
        FROZEN_TIME + timedelta(seconds=300),
        FROZEN_TIME + timedelta(seconds=600),
    ]


@time_machine.travel(FROZEN_TIME, tick=False)
def test_upcoming_once_future():
    run_at = FROZEN_TIME + timedelta(hours=1)
    task = _task(TriggerType.ONCE, {"run_at": run_at.isoformat()})
    times = compute_upcoming_run_times(task, count=5)
    assert times == [run_at]


@time_machine.travel(FROZEN_TIME, tick=False)
def test_upcoming_once_past():
    run_at = FROZEN_TIME - timedelta(hours=1)
    task = _task(TriggerType.ONCE, {"run_at": run_at.isoformat()})
    times = compute_upcoming_run_times(task, count=5)
    assert not times


@time_machine.travel(FROZEN_TIME, tick=False)
def test_upcoming_respects_count():
    task = _task(
        TriggerType.CRON,
        {"expression": "0 9 * * *", "timezone": "UTC"},
    )
    times = compute_upcoming_run_times(task, count=2)
    assert len(times) == 2
