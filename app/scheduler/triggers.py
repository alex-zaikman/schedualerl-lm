from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.enums import TriggerType
from app.db.models.scheduled_task import ScheduledTask
from app.schemas.tasks import (
    CronTriggerSpec,
    CronTriggerConfig,
    IntervalTriggerSpec,
    IntervalTriggerConfig,
    OnceTrigger,
    OnceTriggerConfig,
    TriggerConfig,
    TriggerSpec,
)


def build_trigger(spec: TriggerSpec):
    if isinstance(spec, OnceTrigger):
        run_at = spec.run_at
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        return DateTrigger(run_at)
    if isinstance(spec, CronTriggerSpec):
        return CronTrigger.from_crontab(spec.expression, timezone=ZoneInfo(spec.timezone))
    if isinstance(spec, IntervalTriggerSpec):
        return IntervalTrigger(seconds=spec.seconds)
    raise ValueError(f"Unsupported trigger type: {spec}")


def build_trigger_from_task(task: ScheduledTask):
    spec = _task_to_trigger_spec(task)
    return build_trigger(spec)


def _task_to_trigger_spec(task: ScheduledTask) -> TriggerSpec:
    config = task.trigger_config
    if task.trigger_type == TriggerType.ONCE:
        return OnceTrigger(run_at=datetime.fromisoformat(config["run_at"]))
    if task.trigger_type == TriggerType.CRON:
        return CronTriggerSpec(
            expression=config["expression"],
            timezone=config.get("timezone", "UTC"),
        )
    if task.trigger_type == TriggerType.INTERVAL:
        return IntervalTriggerSpec(seconds=config["seconds"])
    raise ValueError(f"Unsupported trigger type: {task.trigger_type}")


def trigger_config_from_spec(spec: TriggerSpec) -> TriggerConfig:
    if isinstance(spec, OnceTrigger):
        run_at = spec.run_at
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        return OnceTriggerConfig(run_at=run_at.isoformat())
    if isinstance(spec, CronTriggerSpec):
        return CronTriggerConfig(expression=spec.expression, timezone=spec.timezone)
    if isinstance(spec, IntervalTriggerSpec):
        return IntervalTriggerConfig(seconds=spec.seconds)
    raise ValueError(f"Unsupported trigger type: {spec}")


def compute_next_run_at(spec: TriggerSpec) -> datetime | None:
    trigger = build_trigger(spec)
    next_fire = trigger.next()
    if next_fire is None:
        return None
    if next_fire.tzinfo is None:
        return next_fire.replace(tzinfo=timezone.utc)
    return next_fire
