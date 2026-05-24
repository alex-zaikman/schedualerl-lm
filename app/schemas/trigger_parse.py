from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator


class TriggerParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


class TriggerParseResponse(BaseModel):
    trigger_type: Literal["once", "cron", "interval"]
    trigger_config: dict
    next_run_at: datetime | None
