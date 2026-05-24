from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.db.models.scheduled_task import ScheduledTask
from app.enums import TriggerType
from app.schemas.tasks import (
    CronTriggerConfig,
    CronTriggerSpec,
    IntervalTriggerConfig,
    IntervalTriggerSpec,
    OnceTrigger,
    OnceTriggerConfig,
    StructuredTriggerSpec,
    TriggerConfig,
)


def build_trigger(spec: StructuredTriggerSpec):
    match spec:
        case OnceTrigger(run_at=run_at):
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
            return DateTrigger(run_at)
        case CronTriggerSpec(expression=expression, timezone=tz):
            return CronTrigger.from_crontab(expression, timezone=ZoneInfo(tz))
        case IntervalTriggerSpec(seconds=seconds):
            return IntervalTrigger(seconds=seconds)
        case _:
            raise ValueError(f"Unsupported trigger type: {spec}")


def build_trigger_from_task(task: ScheduledTask):
    spec = _task_to_trigger_spec(task)
    return build_trigger(spec)


def _task_to_trigger_spec(task: ScheduledTask) -> StructuredTriggerSpec:
    config = task.trigger_config
    match task.trigger_type:
        case TriggerType.ONCE:
            return OnceTrigger(run_at=datetime.fromisoformat(config["run_at"]))
        case TriggerType.CRON:
            return CronTriggerSpec(
                expression=config["expression"],
                timezone=config.get("timezone", "UTC"),
            )
        case TriggerType.INTERVAL:
            return IntervalTriggerSpec(seconds=config["seconds"])
        case _:
            raise ValueError(f"Unsupported trigger type: {task.trigger_type}")


def trigger_config_from_spec(spec: StructuredTriggerSpec) -> TriggerConfig:
    match spec:
        case OnceTrigger(run_at=run_at):
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
            return OnceTriggerConfig(run_at=run_at.isoformat())
        case CronTriggerSpec(expression=expression, timezone=tz):
            return CronTriggerConfig(expression=expression, timezone=tz)
        case IntervalTriggerSpec(seconds=seconds):
            return IntervalTriggerConfig(seconds=seconds)
        case _:
            raise ValueError(f"Unsupported trigger type: {spec}")


def compute_next_run_at(spec: StructuredTriggerSpec) -> datetime | None:
    trigger = build_trigger(spec)
    next_fire = trigger.next()
    if next_fire is None:
        return None
    if next_fire.tzinfo is None:
        return next_fire.replace(tzinfo=timezone.utc)
    return next_fire


def compute_next_run_at_for_task(task: ScheduledTask) -> datetime | None:
    return compute_next_run_at(_task_to_trigger_spec(task))


def compute_upcoming_run_times(task: ScheduledTask, *, count: int) -> list[datetime]:
    trigger = build_trigger_from_task(task)
    now = datetime.now(timezone.utc)
    times: list[datetime] = []
    for _ in range(count):
        nxt = trigger.next()
        if nxt is None:
            break
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=timezone.utc)
        else:
            nxt = nxt.astimezone(timezone.utc)
        if nxt < now:
            if task.trigger_type == TriggerType.ONCE:
                break
            continue
        times.append(nxt)
    return times
