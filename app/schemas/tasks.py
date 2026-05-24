from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, HttpUrl, field_validator


class OnceTrigger(BaseModel):
    type: Literal["once"] = "once"
    run_at: datetime


class CronTriggerSpec(BaseModel):
    type: Literal["cron"] = "cron"
    expression: str
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


class IntervalTriggerSpec(BaseModel):
    type: Literal["interval"] = "interval"
    seconds: int = Field(gt=0)


TriggerSpec = Annotated[
    OnceTrigger | CronTriggerSpec | IntervalTriggerSpec,
    Field(discriminator="type"),
]


class TaskCreate(BaseModel):
    webhook_url: HttpUrl
    parameters: dict[str, str] = Field(default_factory=dict)
    trigger: TriggerSpec


class TaskResponse(BaseModel):
    id: str
    user_id: str
    webhook_url: str
    parameters: dict[str, str]
    trigger_type: str
    trigger_config: dict
    next_run_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
