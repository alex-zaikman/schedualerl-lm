import pytest

from app.enums import TriggerType
from app.schemas.trigger_parse import (
    IntervalUnit,
    TriggerParseLLMOutput,
    trigger_spec_from_llm_output,
)


def test_trigger_spec_from_llm_output_cron():
    output = TriggerParseLLMOutput.model_validate(
        {
            "_thought": "Daily at 9am.",
            "type": "cron",
            "cron_expr": "0 9 * * *",
            "interval_value": None,
            "interval_unit": None,
            "once_datetime": None,
        }
    )

    spec = trigger_spec_from_llm_output(output, timezone="America/New_York")

    assert spec.type == TriggerType.CRON
    assert spec.expression == "0 9 * * *"
    assert spec.timezone == "America/New_York"


@pytest.mark.parametrize(
    ("value", "unit", "expected_seconds"),
    [
        (5, IntervalUnit.MINUTES, 300),
        (2, IntervalUnit.HOURS, 7200),
        (14, IntervalUnit.DAYS, 1_209_600),
        (2, IntervalUnit.WEEKS, 1_209_600),
        (10, IntervalUnit.SECONDS, 10),
    ],
)
def test_trigger_spec_from_llm_output_interval_math(value, unit, expected_seconds):
    output = TriggerParseLLMOutput.model_validate(
        {
            "_thought": "Fixed interval.",
            "type": "interval",
            "cron_expr": None,
            "interval_value": value,
            "interval_unit": unit,
            "once_datetime": None,
        }
    )

    spec = trigger_spec_from_llm_output(output, timezone="UTC")

    assert spec.type == TriggerType.INTERVAL
    assert spec.seconds == expected_seconds


def test_trigger_spec_from_llm_output_once():
    output = TriggerParseLLMOutput.model_validate(
        {
            "_thought": "One-time run.",
            "type": "once",
            "cron_expr": None,
            "interval_value": None,
            "interval_unit": None,
            "once_datetime": "2026-05-25T09:00:00+00:00",
        }
    )

    spec = trigger_spec_from_llm_output(output, timezone="UTC")

    assert spec.type == TriggerType.ONCE
    assert spec.run_at.isoformat() == "2026-05-25T09:00:00+00:00"


def test_trigger_parse_llm_output_rejects_cron_with_interval_fields():
    with pytest.raises(ValueError, match="only cron_expr should be set"):
        TriggerParseLLMOutput.model_validate(
            {
                "_thought": "Mixed fields.",
                "type": "cron",
                "cron_expr": "0 9 * * *",
                "interval_value": 5,
                "interval_unit": "minutes",
                "once_datetime": None,
            }
        )


def test_trigger_parse_llm_output_rejects_cron_with_once_datetime():
    with pytest.raises(ValueError, match="only cron_expr should be set"):
        TriggerParseLLMOutput.model_validate(
            {
                "_thought": "Daily 11pm with spurious once_datetime.",
                "type": "cron",
                "cron_expr": "0 23 * * *",
                "interval_value": None,
                "interval_unit": None,
                "once_datetime": "2026-05-24T23:00:00+00:00",
            }
        )


def test_trigger_parse_llm_output_requires_interval_unit_pair():
    with pytest.raises(
        ValueError,
        match="interval_value and interval_unit are required",
    ):
        TriggerParseLLMOutput.model_validate(
            {
                "_thought": "Missing unit.",
                "type": "interval",
                "cron_expr": None,
                "interval_value": 5,
                "interval_unit": None,
                "once_datetime": None,
            }
        )
