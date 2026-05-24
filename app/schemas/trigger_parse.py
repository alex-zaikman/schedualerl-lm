from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

from app.enums import TriggerType
from app.schemas.tasks import TriggerConfig


class TriggerParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


class TriggerParseResponse(BaseModel):
    trigger_type: TriggerType
    trigger_config: TriggerConfig
    next_run_at: datetime | None
