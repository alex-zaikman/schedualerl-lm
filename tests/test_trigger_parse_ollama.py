import time_machine

from tests.constants import FROZEN_TIME


@time_machine.travel(FROZEN_TIME, tick=False)
def test_parse_every_day_at_9am(client, auth_headers_frozen, ollama_available):
    response = client.post(
        "/api/v1/triggers/parse",
        headers=auth_headers_frozen,
        json={"text": "every day at 9am UTC", "timezone": "UTC"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trigger_type"] == "cron"
    assert "expression" in body["trigger_config"]
    assert body["trigger_config"]["timezone"] == "UTC"
    assert body["next_run_at"] is not None


@time_machine.travel(FROZEN_TIME, tick=False)
def test_parse_every_5_minutes(client, auth_headers_frozen, ollama_available):
    response = client.post(
        "/api/v1/triggers/parse",
        headers=auth_headers_frozen,
        json={"text": "every 5 minutes"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trigger_type"] == "interval"
    assert body["trigger_config"]["seconds"] == 300
    assert body["next_run_at"] is not None
