from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models.task_history import TaskHistory
from app.enums import SortOrder, TaskHistoryEventType, TriggerType
from app.schemas.execution import WebhookFireResult
from app.schemas.tasks import (
    CronTriggerConfig,
    IntervalTriggerConfig,
    OnceTriggerConfig,
    TriggerConfig,
)


class HistoryListQuery(BaseModel):
    event_type: TaskHistoryEventType | None = Field(
        default=None,
        description="When set, return only entries with this event type.",
    )
    task_id: UUID | None = Field(
        default=None,
        description="When set, return only entries for this task.",
    )
    since: datetime | None = Field(
        default=None,
        description="Inclusive lower bound on created_at.",
    )
    until: datetime | None = Field(
        default=None,
        description="Inclusive upper bound on created_at.",
    )
    order: SortOrder = Field(default=SortOrder.DESC, description="Sort direction by created_at.")
    limit: int = Field(default=50, ge=1, le=100, description="Page size (1-100).")
    offset: int = Field(default=0, ge=0, description="Number of items to skip.")


class HistoryEntryBase(BaseModel):
    id: str = Field(description="History entry UUID.")
    task_id: str = Field(description="Task UUID this entry relates to.")
    created_at: datetime = Field(description="When the event occurred (UTC).")


class TaskCreatedHistoryEntry(HistoryEntryBase):
    event_type: Literal[TaskHistoryEventType.TASK_CREATED] = TaskHistoryEventType.TASK_CREATED
    webhook_url: str
    trigger_type: TriggerType
    trigger_config: TriggerConfig


class TaskActivatedHistoryEntry(HistoryEntryBase):
    event_type: Literal[TaskHistoryEventType.TASK_ACTIVATED] = TaskHistoryEventType.TASK_ACTIVATED


class TaskDeactivatedHistoryEntry(HistoryEntryBase):
    event_type: Literal[TaskHistoryEventType.TASK_DEACTIVATED] = TaskHistoryEventType.TASK_DEACTIVATED


class TaskDeletedHistoryEntry(HistoryEntryBase):
    event_type: Literal[TaskHistoryEventType.TASK_DELETED] = TaskHistoryEventType.TASK_DELETED
    webhook_url: str
    trigger_type: TriggerType
    trigger_config: TriggerConfig


class ExecutionHistoryEntry(HistoryEntryBase, WebhookFireResult):
    event_type: Literal[TaskHistoryEventType.EXECUTION] = TaskHistoryEventType.EXECUTION


HistoryEntry = Annotated[
    TaskCreatedHistoryEntry
    | TaskActivatedHistoryEntry
    | TaskDeactivatedHistoryEntry
    | TaskDeletedHistoryEntry
    | ExecutionHistoryEntry,
    Field(discriminator="event_type"),
]


class HistoryListResponse(BaseModel):
    items: list[HistoryEntry] = Field(description="History entries in this page.")
    total: int = Field(description="Total entries matching the query.")
    limit: int = Field(description="Page size used for this response.")
    offset: int = Field(description="Number of items skipped before this page.")


def _trigger_config_from_row(row: TaskHistory) -> TriggerConfig:
    match row.trigger_type:
        case TriggerType.CRON:
            return CronTriggerConfig(
                expression=row.cron_expression or "",
                timezone=row.cron_timezone or "UTC",
            )
        case TriggerType.INTERVAL:
            return IntervalTriggerConfig(seconds=row.interval_seconds or 0)
        case TriggerType.ONCE:
            return OnceTriggerConfig(run_at=(row.once_run_at or datetime.min).isoformat())
        case _:
            raise ValueError(f"Unsupported trigger type: {row.trigger_type}")


def entry_from_row(row: TaskHistory) -> HistoryEntry:
    base = {
        "id": str(row.id),
        "task_id": str(row.task_id),
        "created_at": row.created_at,
    }
    match row.event_type:
        case TaskHistoryEventType.TASK_CREATED:
            return TaskCreatedHistoryEntry(
                **base,
                webhook_url=row.webhook_url or "",
                trigger_type=row.trigger_type,
                trigger_config=_trigger_config_from_row(row),
            )
        case TaskHistoryEventType.TASK_ACTIVATED:
            return TaskActivatedHistoryEntry(**base)
        case TaskHistoryEventType.TASK_DEACTIVATED:
            return TaskDeactivatedHistoryEntry(**base)
        case TaskHistoryEventType.TASK_DELETED:
            return TaskDeletedHistoryEntry(
                **base,
                webhook_url=row.webhook_url or "",
                trigger_type=row.trigger_type,
                trigger_config=_trigger_config_from_row(row),
            )
        case TaskHistoryEventType.EXECUTION:
            return ExecutionHistoryEntry(
                **base,
                execution_source=row.execution_source,
                webhook_url=row.webhook_url or "",
                http_status=row.http_status,
                error_message=row.error_message,
                success=row.success if row.success is not None else False,
            )
        case _:
            raise ValueError(f"Unsupported event type: {row.event_type}")
