from collections.abc import Callable

import pytest
import time_machine

from tests.constants import FROZEN_TIME

TriggerConfigCheck = Callable[[dict], bool]


def _has_cron_expression(config: dict) -> bool:
    return "expression" in config


def _cron_timezone(timezone: str) -> TriggerConfigCheck:
    def check(config: dict) -> bool:
        return config.get("timezone") == timezone and "expression" in config

    return check


def _cron_hour_minute(hour: int, minute: int = 0) -> TriggerConfigCheck:
    def check(config: dict) -> bool:
        expression = config.get("expression", "")
        parts = expression.split()
        if len(parts) != 5:
            return False
        return parts[0] == str(minute) and parts[1] == str(hour)

    return check


def _interval_seconds(expected: int) -> TriggerConfigCheck:
    def check(config: dict) -> bool:
        return config.get("seconds") == expected

    return check


TEXT_TRIGGER_CASES = [
    pytest.param(
        "every day at 9am UTC",
        "UTC",
        "cron",
        _has_cron_expression,
        id="daily_9am_utc",
    ),
    pytest.param(
        "every 5 minutes",
        "UTC",
        "interval",
        _interval_seconds(300),
        id="every_5_minutes",
    ),
    pytest.param(
        "every 30 seconds",
        "UTC",
        "interval",
        _interval_seconds(30),
        id="every_30_seconds",
    ),
    pytest.param(
        "every Saturday at 9am",
        "UTC",
        "cron",
        _has_cron_expression,
        id="saturday_9am",
    ),
    pytest.param(
        "every 2 hours",
        "UTC",
        "interval",
        _interval_seconds(7200),
        id="every_2_hours",
    ),
    pytest.param(
        "every weekday at 8am",
        "UTC",
        "cron",
        _has_cron_expression,
        id="weekday_8am",
    ),
    pytest.param(
        "every day at 11pm UTC",
        "UTC",
        "cron",
        _cron_hour_minute(23),
        id="daily_11pm_utc",
    ),
    pytest.param(
        "every 10 minutes",
        "UTC",
        "interval",
        _interval_seconds(600),
        id="every_10_minutes",
    ),
    pytest.param(
        "every 15 minutes",
        "UTC",
        "interval",
        _interval_seconds(900),
        id="every_15_minutes",
    ),
    pytest.param(
        "every 45 minutes",
        "UTC",
        "interval",
        _interval_seconds(2700),
        id="every_45_minutes",
    ),
    pytest.param(
        "every 7 days",
        "UTC",
        "interval",
        _interval_seconds(604800),
        id="every_7_days",
    ),
    pytest.param(
        "every two weeks",
        "UTC",
        "interval",
        _interval_seconds(1209600),
        id="every_two_weeks",
    ),
    pytest.param(
        "every Monday at 9am",
        "UTC",
        "cron",
        _has_cron_expression,
        id="monday_9am",
    ),
    pytest.param(
        "every Sunday morning",
        "UTC",
        "cron",
        _cron_hour_minute(9),
        id="sunday_morning",
    ),
    pytest.param(
        "every day at 9:30 pm",
        "UTC",
        "cron",
        _cron_hour_minute(23, 30),
        id="daily_930pm",
    ),
    pytest.param(
        "every day at noon",
        "UTC",
        "cron",
        _cron_hour_minute(12),
        id="daily_noon",
    ),
    pytest.param(
        "every day at midnight",
        "UTC",
        "cron",
        _cron_hour_minute(0),
        id="daily_midnight",
    ),
    pytest.param(
        "every Saturday morning",
        "UTC",
        "cron",
        _has_cron_expression,
        id="saturday_morning",
    ),
    pytest.param(
        "every other week on Saturday morning",
        "UTC",
        "cron",
        _cron_hour_minute(9),
        id="biweekly_saturday_morning",
    ),
    pytest.param(
        "every day at 9am",
        "America/New_York",
        "cron",
        _cron_timezone("America/New_York"),
        id="daily_9am_eastern",
    ),
    pytest.param(
        "every 1 hour",
        "UTC",
        "interval",
        _interval_seconds(3600),
        id="every_1_hour",
    ),
    pytest.param(
        "every day at 11am",
        "UTC",
        "cron",
        _cron_hour_minute(11),
        id="daily_11am",
    ),
]


@time_machine.travel(FROZEN_TIME, tick=False)
@pytest.mark.parametrize(
    "text,timezone,expected_type,check_config",
    TEXT_TRIGGER_CASES,
)
def test_create_task_text_trigger_ollama(
    client,
    auth_headers_frozen,
    ollama_available,
    text: str,
    timezone: str,
    expected_type: str,
    check_config: TriggerConfigCheck,
):
    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {"type": "text", "text": text, "timezone": timezone},
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["trigger_type"] == expected_type
    assert check_config(body["trigger_config"])
    assert body["next_run_at"] is not None
