from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.enums import TriggerType


class OnceTrigger(BaseModel):
    type: Literal[TriggerType.ONCE] = TriggerType.ONCE
    run_at: datetime = Field(
        description="UTC or timezone-aware datetime when the task should fire.",
    )


class CronTriggerSpec(BaseModel):
    type: Literal[TriggerType.CRON] = TriggerType.CRON
    expression: str = Field(
        description="Standard 5-field cron expression (minute hour day month weekday).",
        examples=["0 9 * * *"],
    )
    timezone: str = Field(
        default="UTC",
        description="IANA timezone name used to interpret the cron expression.",
        examples=["UTC", "America/New_York"],
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


class IntervalTriggerSpec(BaseModel):
    type: Literal[TriggerType.INTERVAL] = TriggerType.INTERVAL
    seconds: int = Field(
        gt=0,
        description="Seconds between runs.",
        examples=[3600],
    )


StructuredTriggerSpec = Annotated[
    OnceTrigger | CronTriggerSpec | IntervalTriggerSpec,
    Field(discriminator="type"),
]


class TextTriggerSpec(BaseModel):
    type: Literal["text"] = "text"
    text: str = Field(
        min_length=1,
        max_length=2000,
        description="Human-readable schedule description.",
        examples=["every day at 9am", "in 30 minutes"],
    )
    timezone: str = Field(
        default="UTC",
        description="IANA timezone name used when parsing relative or local-time phrases.",
        examples=["UTC", "America/New_York"],
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


TriggerSpec = Annotated[
    OnceTrigger | CronTriggerSpec | IntervalTriggerSpec | TextTriggerSpec,
    Field(
        discriminator="type",
        description=(
            "Schedule specification. Prefer type 'text' for natural language; "
            "use structured types when the schedule is already known."
        ),
    ),
]


class TaskCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "webhook_url": "https://example.com/hook",
                    "parameters": {"source": "schedulerlm"},
                    "trigger": {
                        "type": "text",
                        "text": "every day at 9am",
                        "timezone": "UTC",
                    },
                },
                {
                    "webhook_url": "https://example.com/hook",
                    "trigger": {
                        "type": "cron",
                        "expression": "0 9 * * *",
                        "timezone": "UTC",
                    },
                },
                {
                    "webhook_url": "https://example.com/hook",
                    "trigger": {"type": "interval", "seconds": 3600},
                },
                {
                    "webhook_url": "https://example.com/hook",
                    "trigger": {
                        "type": "once",
                        "run_at": "2026-06-01T09:00:00+00:00",
                    },
                },
            ]
        }
    )

    webhook_url: HttpUrl = Field(
        description="URL called via HTTP GET when the task fires.",
        examples=["https://example.com/hook"],
    )
    parameters: dict[str, str] = Field(
        default_factory=dict,
        description="Query parameters appended to the webhook GET request.",
        examples=[{"key": "value"}],
    )
    trigger: TriggerSpec


class TaskListQuery(BaseModel):
    active_only: bool = Field(
        default=True,
        description="When true, return only tasks that are currently scheduled.",
    )
    limit: int = Field(default=50, ge=1, le=100, description="Page size (1–100).")
    offset: int = Field(default=0, ge=0, description="Number of items to skip.")


class OnceTriggerConfig(BaseModel):
    run_at: str = Field(description="ISO 8601 datetime when the task will fire.")


class CronTriggerConfig(BaseModel):
    expression: str = Field(
        description="5-field cron expression (minute hour day month weekday)."
    )
    timezone: str = Field(
        default="UTC",
        description="IANA timezone used to interpret the cron expression.",
    )


class IntervalTriggerConfig(BaseModel):
    seconds: int = Field(description="Seconds between runs.")


TriggerConfig = OnceTriggerConfig | CronTriggerConfig | IntervalTriggerConfig


class TaskResponse(BaseModel):
    id: str = Field(description="Task UUID.")
    user_id: str = Field(description="Owner user id (JWT `sub` claim).")
    webhook_url: str = Field(description="URL called via HTTP GET when the task fires.")
    parameters: dict[str, str] = Field(
        description="Query parameters sent on the webhook GET request.",
    )
    trigger_type: TriggerType = Field(
        description="Resolved trigger kind stored for the task (`once`, `cron`, or `interval`).",
    )
    trigger_config: TriggerConfig = Field(
        description="Structured trigger configuration matching `trigger_type`.",
    )
    next_run_at: datetime | None = Field(
        description="Next scheduled fire time in UTC, or null if inactive.",
    )
    is_active: bool = Field(description="Whether the task is currently scheduled.")
    created_at: datetime = Field(description="When the task was created (UTC).")
    updated_at: datetime = Field(description="When the task was last updated (UTC).")

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    items: list[TaskResponse] = Field(description="Tasks in this page.")
    total: int = Field(description="Total tasks matching the query (across all pages).")
    limit: int = Field(description="Page size used for this response.")
    offset: int = Field(description="Number of items skipped before this page.")
