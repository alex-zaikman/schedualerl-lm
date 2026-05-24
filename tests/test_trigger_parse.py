import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import time_machine

from tests.constants import FROZEN_TIME


def _mock_llm_response(content: str | dict) -> MagicMock:
    if isinstance(content, dict):
        content = json.dumps(content)
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


@time_machine.travel(FROZEN_TIME, tick=False)
@patch("app.services.trigger_parse.completion")
def test_parse_trigger_cron(mock_completion, client, auth_headers_frozen):
    mock_completion.return_value = _mock_llm_response(
        {"type": "cron", "expression": "0 9 * * *", "timezone": "UTC"}
    )

    response = client.post(
        "/api/v1/triggers/parse",
        headers=auth_headers_frozen,
        json={"text": "every day at 9am UTC"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trigger_type"] == "cron"
    assert body["trigger_config"] == {"expression": "0 9 * * *", "timezone": "UTC"}
    assert body["next_run_at"] is not None


@time_machine.travel(FROZEN_TIME, tick=False)
@patch("app.services.trigger_parse.completion")
def test_parse_trigger_interval(mock_completion, client, auth_headers_frozen):
    mock_completion.return_value = _mock_llm_response({"type": "interval", "seconds": 300})

    response = client.post(
        "/api/v1/triggers/parse",
        headers=auth_headers_frozen,
        json={"text": "every 5 minutes"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trigger_type"] == "interval"
    assert body["trigger_config"] == {"seconds": 300}
    assert body["next_run_at"] is not None


@time_machine.travel(FROZEN_TIME, tick=False)
@patch("app.services.trigger_parse.completion")
def test_parse_trigger_once(mock_completion, client, auth_headers_frozen):
    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    mock_completion.return_value = _mock_llm_response({"type": "once", "run_at": run_at})

    response = client.post(
        "/api/v1/triggers/parse",
        headers=auth_headers_frozen,
        json={"text": "in one hour"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trigger_type"] == "once"
    assert body["trigger_config"]["run_at"] == run_at
    assert body["next_run_at"] is not None


@time_machine.travel(FROZEN_TIME, tick=False)
@patch("app.services.trigger_parse.completion")
def test_parse_trigger_retries_on_invalid_cron(mock_completion, client, auth_headers_frozen):
    mock_completion.side_effect = [
        _mock_llm_response({"type": "cron", "expression": "*/61 * * * *", "timezone": "UTC"}),
        _mock_llm_response({"type": "cron", "expression": "0 9 * * *", "timezone": "UTC"}),
    ]

    response = client.post(
        "/api/v1/triggers/parse",
        headers=auth_headers_frozen,
        json={"text": "every day at 9am"},
    )

    assert response.status_code == 200
    assert mock_completion.call_count == 2
    body = response.json()
    assert body["trigger_type"] == "cron"
    assert body["trigger_config"]["expression"] == "0 9 * * *"


@time_machine.travel(FROZEN_TIME, tick=False)
@patch("app.services.trigger_parse.completion")
def test_parse_trigger_exhausted_retries_returns_422(mock_completion, client, auth_headers_frozen):
    mock_completion.return_value = _mock_llm_response(
        {"type": "cron", "expression": "*/61 * * * *", "timezone": "UTC"}
    )

    response = client.post(
        "/api/v1/triggers/parse",
        headers=auth_headers_frozen,
        json={"text": "every day at 9am"},
    )

    assert response.status_code == 422
    assert "Invalid cron expression" in response.json()["detail"]
    assert mock_completion.call_count == 3


def test_parse_trigger_requires_auth(client):
    response = client.post(
        "/api/v1/triggers/parse",
        json={"text": "every day at 9am"},
    )

    assert response.status_code == 401
