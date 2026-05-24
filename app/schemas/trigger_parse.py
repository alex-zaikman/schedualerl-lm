from datetime import datetime
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import TriggerType
from app.schemas.tasks import (
    CronTriggerSpec,
    IntervalTriggerSpec,
    OnceTrigger,
    StructuredTriggerSpec,
    TriggerConfig,
)


class IntervalUnit(StrEnum):
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"


INTERVAL_UNIT_SECONDS: dict[IntervalUnit, int] = {
    IntervalUnit.SECONDS: 1,
    IntervalUnit.MINUTES: 60,
    IntervalUnit.HOURS: 3600,
    IntervalUnit.DAYS: 86400,
    IntervalUnit.WEEKS: 604_800,
}


class TriggerParseLLMOutput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    thought: str = Field(alias="_thought", min_length=1)
    type: Literal["cron", "interval", "once"]
    cron_expr: str | None
    interval_value: int | None
    interval_unit: IntervalUnit | None
    once_datetime: str | None

    @model_validator(mode="after")
    def validate_type_fields(self) -> "TriggerParseLLMOutput":
        match self.type:
            case "cron":
                if not self.cron_expr:
                    raise ValueError("cron_expr is required for cron triggers")
                if (
                    self.interval_value is not None
                    or self.interval_unit is not None
                    or self.once_datetime is not None
                ):
                    raise ValueError("only cron_expr should be set for cron triggers")
            case "interval":
                if self.interval_value is None or self.interval_unit is None:
                    raise ValueError("interval_value and interval_unit are required for interval triggers")
                if self.interval_value <= 0:
                    raise ValueError("interval_value must be positive")
                if self.cron_expr is not None or self.once_datetime is not None:
                    raise ValueError("only interval_value and interval_unit should be set for interval triggers")
            case "once":
                if not self.once_datetime:
                    raise ValueError("once_datetime is required for once triggers")
                if (
                    self.cron_expr is not None
                    or self.interval_value is not None
                    or self.interval_unit is not None
                ):
                    raise ValueError("only once_datetime should be set for once triggers")
        return self


def trigger_spec_from_llm_output(
    output: TriggerParseLLMOutput,
    *,
    timezone: str,
) -> StructuredTriggerSpec:
    match output.type:
        case "cron":
            assert output.cron_expr is not None
            return CronTriggerSpec(expression=output.cron_expr, timezone=timezone)
        case "interval":
            assert output.interval_value is not None and output.interval_unit is not None
            seconds = output.interval_value * INTERVAL_UNIT_SECONDS[output.interval_unit]
            return IntervalTriggerSpec(seconds=seconds)
        case "once":
            assert output.once_datetime is not None
            return OnceTrigger(run_at=datetime.fromisoformat(output.once_datetime))


class TriggerParseRequest(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=2000,
        description="Natural-language schedule text to parse into a structured trigger.",
        examples=["every day at 9am", "every 2 hours"],
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


class TriggerParseResponse(BaseModel):
    trigger_type: TriggerType = Field(
        description="Parsed trigger kind (`once`, `cron`, or `interval`).",
    )
    trigger_config: TriggerConfig = Field(
        description="Structured trigger configuration matching `trigger_type`.",
    )
    next_run_at: datetime | None = Field(
        description="Next scheduled fire time in UTC, or null if none can be computed.",
    )
