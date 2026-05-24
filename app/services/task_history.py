from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.scheduled_task import ScheduledTask
from app.db.models.task_history import TaskHistory
from app.enums import ExecutionSource, TaskHistoryEventType, TriggerType


def _trigger_columns(trigger_type: str, trigger_config: dict) -> dict:
    match trigger_type:
        case TriggerType.CRON:
            return {
                "cron_expression": trigger_config["expression"],
                "cron_timezone": trigger_config.get("timezone", "UTC"),
                "interval_seconds": None,
                "once_run_at": None,
            }
        case TriggerType.INTERVAL:
            return {
                "cron_expression": None,
                "cron_timezone": None,
                "interval_seconds": trigger_config["seconds"],
                "once_run_at": None,
            }
        case TriggerType.ONCE:
            run_at = trigger_config["run_at"]
            if isinstance(run_at, str):
                parsed = datetime.fromisoformat(run_at.replace("Z", "+00:00"))
            else:
                parsed = run_at
            return {
                "cron_expression": None,
                "cron_timezone": None,
                "interval_seconds": None,
                "once_run_at": parsed,
            }
        case _:
            raise ValueError(f"Unsupported trigger type: {trigger_type}")


def _snapshot_from_task(task: ScheduledTask) -> dict:
    columns = _trigger_columns(task.trigger_type, task.trigger_config)
    return {
        "webhook_url": task.webhook_url,
        "trigger_type": task.trigger_type,
        **columns,
    }


async def record_task_created(
    session: AsyncSession,
    *,
    user_id: str,
    task: ScheduledTask,
) -> None:
    session.add(
        TaskHistory(
            id=uuid4(),
            user_id=user_id,
            task_id=task.id,
            event_type=TaskHistoryEventType.TASK_CREATED,
            **_snapshot_from_task(task),
        )
    )


async def record_task_lifecycle(
    session: AsyncSession,
    *,
    user_id: str,
    task_id: UUID,
    event_type: TaskHistoryEventType,
) -> None:
    session.add(
        TaskHistory(
            id=uuid4(),
            user_id=user_id,
            task_id=task_id,
            event_type=event_type,
        )
    )


async def record_task_deleted(
    session: AsyncSession,
    *,
    user_id: str,
    task: ScheduledTask,
) -> None:
    session.add(
        TaskHistory(
            id=uuid4(),
            user_id=user_id,
            task_id=task.id,
            event_type=TaskHistoryEventType.TASK_DELETED,
            **_snapshot_from_task(task),
        )
    )


async def record_execution(
    session: AsyncSession,
    *,
    user_id: str,
    task_id: UUID,
    execution_source: ExecutionSource,
    webhook_url: str,
    success: bool,
    http_status: int | None,
    error_message: str | None,
) -> None:
    session.add(
        TaskHistory(
            id=uuid4(),
            user_id=user_id,
            task_id=task_id,
            event_type=TaskHistoryEventType.EXECUTION,
            webhook_url=webhook_url,
            execution_source=execution_source,
            http_status=http_status,
            error_message=error_message,
            success=success,
        )
    )
