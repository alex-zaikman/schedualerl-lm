from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.enums import TriggerType


class OnceTrigger(BaseModel):
    type: Literal[TriggerType.ONCE] = TriggerType.ONCE
    run_at: datetime


class CronTriggerSpec(BaseModel):
    type: Literal[TriggerType.CRON] = TriggerType.CRON
    expression: str
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


class IntervalTriggerSpec(BaseModel):
    type: Literal[TriggerType.INTERVAL] = TriggerType.INTERVAL
    seconds: int = Field(gt=0)


StructuredTriggerSpec = Annotated[
    OnceTrigger | CronTriggerSpec | IntervalTriggerSpec,
    Field(discriminator="type"),
]


class TextTriggerSpec(BaseModel):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=2000)
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


TriggerSpec = Annotated[
    OnceTrigger | CronTriggerSpec | IntervalTriggerSpec | TextTriggerSpec,
    Field(discriminator="type"),
]


class TaskCreate(BaseModel):
    webhook_url: HttpUrl
    parameters: dict[str, str] = Field(default_factory=dict)
    trigger: TriggerSpec


class TaskListQuery(BaseModel):
    active_only: bool = True
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class OnceTriggerConfig(BaseModel):
    run_at: str


class CronTriggerConfig(BaseModel):
    expression: str
    timezone: str = "UTC"


class IntervalTriggerConfig(BaseModel):
    seconds: int


TriggerConfig = OnceTriggerConfig | CronTriggerConfig | IntervalTriggerConfig


class TaskResponse(BaseModel):
    id: str
    user_id: str
    webhook_url: str
    parameters: dict[str, str]
    trigger_type: TriggerType
    trigger_config: TriggerConfig
    next_run_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    limit: int
    offset: int
