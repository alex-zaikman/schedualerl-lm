from collections.abc import Callable

import pytest
import time_machine

from tests.constants import FROZEN_TIME

TriggerConfigCheck = Callable[[dict], bool]


def _has_cron_expression(config: dict) -> bool:
    return "expression" in config


def _interval_seconds(expected: int) -> TriggerConfigCheck:
    def check(config: dict) -> bool:
        return config.get("seconds") == expected

    return check


def _has_run_at(config: dict) -> bool:
    return "run_at" in config


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
        "in one hour",
        "UTC",
        "once",
        _has_run_at,
        id="in_one_hour",
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
        "tomorrow at 3pm",
        "UTC",
        "once",
        _has_run_at,
        id="tomorrow_3pm",
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
