from datetime import timedelta
from uuid import uuid4

import httpx
import jwt
import time_machine

from app.auth.jwt import decode_token
from app.scheduler.executor import init_executor
from tests.constants import FROZEN_TIME, TEST_USER_ID


def _init_mock_executor(client, test_settings, handler):
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    init_executor(
        client.app.state.session_factory,
        test_settings,
        http_client,
        client.app.state.scheduler,
    )
    client.app.state._test_http_client = http_client  # pylint: disable=protected-access
    return http_client


@time_machine.travel(FROZEN_TIME, tick=False)
def test_run_task_fires_webhook(client, test_settings, auth_headers_frozen):
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200)

    _init_mock_executor(client, test_settings, handler)

    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    create_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {"q": "1"},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    task_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/tasks/{task_id}/run",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == task_id
    assert body["http_status"] == 200

    payload = decode_token(
        captured["authorization"].removeprefix("Bearer "),
        test_settings.auth,
    )
    assert payload["sub"] == TEST_USER_ID
    assert payload["task_id"] == task_id
    assert payload["purpose"] == "webhook"


@time_machine.travel(FROZEN_TIME, tick=False)
def test_run_task_on_paused_task(client, test_settings, auth_headers_frozen):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    _init_mock_executor(client, test_settings, handler)

    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    create_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    task_id = create_response.json()["id"]

    deactivate_response = client.post(
        f"/api/v1/tasks/{task_id}/deactivate",
        headers=auth_headers_frozen,
    )
    assert deactivate_response.json()["is_active"] is False

    response = client.post(
        f"/api/v1/tasks/{task_id}/run",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 200
    assert response.json()["http_status"] == 200

    task_response = client.get(
        "/api/v1/tasks?active_only=false",
        headers=auth_headers_frozen,
    )
    task = next(item for item in task_response.json()["items"] if item["id"] == task_id)
    assert task["is_active"] is False


@time_machine.travel(FROZEN_TIME, tick=False)
def test_run_once_task_stays_active(client, test_settings, auth_headers_frozen):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    _init_mock_executor(client, test_settings, handler)

    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    create_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    task_id = create_response.json()["id"]
    expected_next_run_at = create_response.json()["next_run_at"]

    response = client.post(
        f"/api/v1/tasks/{task_id}/run",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 200

    list_response = client.get("/api/v1/tasks", headers=auth_headers_frozen)
    task = list_response.json()["items"][0]
    assert task["is_active"] is True
    assert task["next_run_at"] == expected_next_run_at


@time_machine.travel(FROZEN_TIME, tick=False)
def test_run_task_webhook_failure_returns_502(
    client, test_settings, auth_headers_frozen
):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    _init_mock_executor(client, test_settings, handler)

    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    create_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    task_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/tasks/{task_id}/run",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 502
    assert "Webhook returned 500" in response.json()["detail"]


@time_machine.travel(FROZEN_TIME, tick=False)
def test_run_task_not_found(client, auth_headers_frozen):
    response = client.post(
        f"/api/v1/tasks/{uuid4()}/run",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 404


@time_machine.travel(FROZEN_TIME, tick=False)
def test_run_task_cross_user_isolation(client, auth_headers_frozen, test_settings):
    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    create_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    task_id = create_response.json()["id"]

    other_token = jwt.encode(
        {
            "sub": "other-user-456",
            "exp": FROZEN_TIME + timedelta(hours=1),
        },
        test_settings.auth.jwt_secret.get_secret_value(),
        algorithm=test_settings.auth.jwt_algorithm,
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}

    response = client.post(
        f"/api/v1/tasks/{task_id}/run",
        headers=other_headers,
    )
    assert response.status_code == 404


@time_machine.travel(FROZEN_TIME, tick=False)
def test_schedule_cron_task(client, auth_headers_frozen):
    create_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {
                "type": "cron",
                "expression": "0 9 * * *",
                "timezone": "UTC",
            },
        },
    )
    task_id = create_response.json()["id"]
    expected_next = create_response.json()["next_run_at"]

    response = client.get(
        f"/api/v1/tasks/{task_id}/schedule",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["trigger_type"] == "cron"
    assert body["is_active"] is True
    assert len(body["upcoming"]) == 5
    assert body["next_run_at"] == expected_next
    assert body["upcoming"][0] == expected_next


@time_machine.travel(FROZEN_TIME, tick=False)
def test_schedule_once_task(client, auth_headers_frozen):
    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    create_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    task_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/tasks/{task_id}/schedule",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["trigger_type"] == "once"
    assert len(body["upcoming"]) == 1
    assert body["next_run_at"] == run_at.replace("+00:00", "Z")


@time_machine.travel(FROZEN_TIME, tick=False)
def test_schedule_count_param(client, auth_headers_frozen):
    create_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {
                "type": "cron",
                "expression": "0 9 * * *",
                "timezone": "UTC",
            },
        },
    )
    task_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/tasks/{task_id}/schedule?count=2",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 200
    assert len(response.json()["upcoming"]) == 2


@time_machine.travel(FROZEN_TIME, tick=False)
def test_schedule_inactive_task(client, auth_headers_frozen):
    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    create_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    task_id = create_response.json()["id"]
    client.post(
        f"/api/v1/tasks/{task_id}/deactivate",
        headers=auth_headers_frozen,
    )

    response = client.get(
        f"/api/v1/tasks/{task_id}/schedule",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is False
    assert len(body["upcoming"]) == 1


@time_machine.travel(FROZEN_TIME, tick=False)
def test_schedule_not_found(client, auth_headers_frozen):
    response = client.get(
        f"/api/v1/tasks/{uuid4()}/schedule",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 404


@time_machine.travel(FROZEN_TIME, tick=False)
def test_schedule_cross_user_isolation(client, auth_headers_frozen, test_settings):
    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    create_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    task_id = create_response.json()["id"]

    other_token = jwt.encode(
        {
            "sub": "other-user-456",
            "exp": FROZEN_TIME + timedelta(hours=1),
        },
        test_settings.auth.jwt_secret.get_secret_value(),
        algorithm=test_settings.auth.jwt_algorithm,
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}

    response = client.get(
        f"/api/v1/tasks/{task_id}/schedule",
        headers=other_headers,
    )
    assert response.status_code == 404


@time_machine.travel(FROZEN_TIME, tick=False)
def test_list_filter_by_trigger_type(client, auth_headers_frozen):
    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/cron",
            "parameters": {},
            "trigger": {
                "type": "cron",
                "expression": "0 9 * * *",
                "timezone": "UTC",
            },
        },
    )
    client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/once",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )

    response = client.get(
        "/api/v1/tasks?trigger_type=cron",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["trigger_type"] == "cron"


@time_machine.travel(FROZEN_TIME, tick=False)
def test_list_sort_by_next_run_at_asc(client, auth_headers_frozen):
    sooner = (FROZEN_TIME + timedelta(minutes=15)).isoformat()
    later = (FROZEN_TIME + timedelta(hours=2)).isoformat()
    sooner_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/sooner",
            "parameters": {},
            "trigger": {"type": "once", "run_at": sooner},
        },
    )
    later_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/later",
            "parameters": {},
            "trigger": {"type": "once", "run_at": later},
        },
    )

    response = client.get(
        "/api/v1/tasks?sort=next_run_at&order=asc",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [sooner_response.json()["id"], later_response.json()["id"]]


@time_machine.travel(FROZEN_TIME, tick=False)
def test_list_sort_by_updated_at(client, auth_headers_frozen):
    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    first_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/first",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    second_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/second",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    client.post(
        f"/api/v1/tasks/{first_response.json()['id']}/deactivate",
        headers=auth_headers_frozen,
    )

    response = client.get(
        "/api/v1/tasks?active_only=false&sort=updated_at&order=desc",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids[0] == first_response.json()["id"]
    assert second_response.json()["id"] in ids


@time_machine.travel(FROZEN_TIME, tick=False)
def test_list_defaults_unchanged(client, auth_headers_frozen):
    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    task_ids: list[str] = []
    for index in range(2):
        response = client.post(
            "/api/v1/tasks",
            headers=auth_headers_frozen,
            json={
                "webhook_url": f"https://example.com/hook/{index}",
                "parameters": {},
                "trigger": {"type": "once", "run_at": run_at},
            },
        )
        task_ids.append(response.json()["id"])

    response = client.get("/api/v1/tasks", headers=auth_headers_frozen)
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == list(reversed(task_ids))
