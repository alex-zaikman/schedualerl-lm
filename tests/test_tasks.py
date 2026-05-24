from datetime import timedelta
from unittest.mock import MagicMock, patch

import httpx
import jwt
import time_machine
from sqlalchemy import select

from app.auth.jwt import decode_token, encode_token
from app.db.models.scheduled_task import ScheduledTask
from app.db.rls import set_scheduler_rls
from tests.constants import FROZEN_TIME, TEST_USER_ID


def _mock_llm_response(content: dict) -> MagicMock:
    import json

    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = json.dumps(
        {
            "_thought": "test reasoning",
            "type": content["type"],
            "cron_expr": content.get("expression"),
            "interval_value": content.get("interval_value"),
            "interval_unit": content.get("interval_unit"),
            "once_datetime": content.get("run_at"),
        }
    )
    return response


@time_machine.travel(FROZEN_TIME, tick=False)
@patch("app.services.trigger_parse.completion")
def test_create_task_with_text_trigger(mock_completion, client, auth_headers_frozen):
    mock_completion.return_value = _mock_llm_response(
        {"type": "cron", "expression": "0 9 * * *"}
    )

    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {"type": "text", "text": "every day at 9am UTC"},
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["trigger_type"] == "cron"
    assert body["trigger_config"] == {"expression": "0 9 * * *", "timezone": "UTC"}
    assert body["next_run_at"] is not None


@time_machine.travel(FROZEN_TIME, tick=False)
@patch("app.services.trigger_parse.completion")
def test_create_task_text_trigger_parse_failure_returns_422(
    mock_completion, client, auth_headers_frozen
):
    mock_completion.return_value = _mock_llm_response(
        {"type": "cron", "expression": "*/61 * * * *", "timezone": "UTC"}
    )

    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {"type": "text", "text": "every day at 9am"},
        },
    )

    assert response.status_code == 422
    assert "Invalid cron expression" in response.json()["detail"]
    assert mock_completion.call_count == 2


@time_machine.travel(FROZEN_TIME, tick=False)
def test_create_and_list_tasks(client, auth_headers_frozen):
    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {"foo": "bar"},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == TEST_USER_ID
    assert body["webhook_url"] == "https://example.com/hook"
    assert body["parameters"] == {"foo": "bar"}
    assert body["trigger_type"] == "once"
    assert body["is_active"] is True
    assert body["id"]

    list_response = client.get("/api/v1/tasks", headers=auth_headers_frozen)
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["total"] == 1
    assert list_body["limit"] == 50
    assert list_body["offset"] == 0
    assert len(list_body["items"]) == 1
    assert list_body["items"][0]["id"] == body["id"]


@time_machine.travel(FROZEN_TIME, tick=False)
def test_list_tasks_pagination(client, auth_headers_frozen):
    run_at = (FROZEN_TIME + timedelta(hours=1)).isoformat()
    task_ids: list[str] = []
    for index in range(3):
        response = client.post(
            "/api/v1/tasks",
            headers=auth_headers_frozen,
            json={
                "webhook_url": f"https://example.com/hook/{index}",
                "parameters": {},
                "trigger": {"type": "once", "run_at": run_at},
            },
        )
        assert response.status_code == 201
        task_ids.append(response.json()["id"])

    page_one = client.get(
        "/api/v1/tasks?limit=2&offset=0",
        headers=auth_headers_frozen,
    )
    assert page_one.status_code == 200
    page_one_body = page_one.json()
    assert page_one_body["total"] == 3
    assert page_one_body["limit"] == 2
    assert page_one_body["offset"] == 0
    assert len(page_one_body["items"]) == 2
    assert [item["id"] for item in page_one_body["items"]] == list(reversed(task_ids))[:2]

    page_two = client.get(
        "/api/v1/tasks?limit=2&offset=2",
        headers=auth_headers_frozen,
    )
    assert page_two.status_code == 200
    page_two_body = page_two.json()
    assert page_two_body["total"] == 3
    assert page_two_body["limit"] == 2
    assert page_two_body["offset"] == 2
    assert len(page_two_body["items"]) == 1
    assert page_two_body["items"][0]["id"] == task_ids[0]


@time_machine.travel(FROZEN_TIME, tick=False)
def test_deactivate_task(client, auth_headers_frozen):
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
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    deactivate_response = client.post(
        f"/api/v1/tasks/{task_id}/deactivate",
        headers=auth_headers_frozen,
    )
    assert deactivate_response.status_code == 200
    body = deactivate_response.json()
    assert body["id"] == task_id
    assert body["is_active"] is False
    assert body["next_run_at"] is None

    active_list = client.get("/api/v1/tasks", headers=auth_headers_frozen)
    assert active_list.status_code == 200
    active_body = active_list.json()
    assert active_body["total"] == 0
    assert active_body["items"] == []

    all_tasks = client.get(
        "/api/v1/tasks?active_only=false",
        headers=auth_headers_frozen,
    )
    assert all_tasks.status_code == 200
    all_body = all_tasks.json()
    assert all_body["total"] == 1
    assert len(all_body["items"]) == 1
    assert all_body["items"][0]["is_active"] is False


@time_machine.travel(FROZEN_TIME, tick=False)
def test_deactivate_task_idempotent(client, auth_headers_frozen):
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

    first = client.post(
        f"/api/v1/tasks/{task_id}/deactivate",
        headers=auth_headers_frozen,
    )
    second = client.post(
        f"/api/v1/tasks/{task_id}/deactivate",
        headers=auth_headers_frozen,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["is_active"] is False


@time_machine.travel(FROZEN_TIME, tick=False)
def test_deactivate_task_not_found(client, auth_headers_frozen):
    from uuid import uuid4

    response = client.post(
        f"/api/v1/tasks/{uuid4()}/deactivate",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 404


@time_machine.travel(FROZEN_TIME, tick=False)
def test_deactivate_task_cross_user_isolation(
    client, auth_headers_frozen, test_settings
):
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
        f"/api/v1/tasks/{task_id}/deactivate",
        headers=other_headers,
    )
    assert response.status_code == 404


@time_machine.travel(FROZEN_TIME, tick=False)
def test_activate_task_after_deactivate(client, auth_headers_frozen):
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

    deactivate_response = client.post(
        f"/api/v1/tasks/{task_id}/deactivate",
        headers=auth_headers_frozen,
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False

    activate_response = client.post(
        f"/api/v1/tasks/{task_id}/activate",
        headers=auth_headers_frozen,
    )
    assert activate_response.status_code == 200
    body = activate_response.json()
    assert body["id"] == task_id
    assert body["is_active"] is True
    assert body["next_run_at"] == expected_next_run_at

    active_list = client.get("/api/v1/tasks", headers=auth_headers_frozen)
    assert active_list.status_code == 200
    active_body = active_list.json()
    assert active_body["total"] == 1
    assert len(active_body["items"]) == 1
    assert active_body["items"][0]["is_active"] is True


@time_machine.travel(FROZEN_TIME, tick=False)
def test_activate_cron_task_after_deactivate(client, auth_headers_frozen):
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
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    deactivate_response = client.post(
        f"/api/v1/tasks/{task_id}/deactivate",
        headers=auth_headers_frozen,
    )
    assert deactivate_response.status_code == 200

    activate_response = client.post(
        f"/api/v1/tasks/{task_id}/activate",
        headers=auth_headers_frozen,
    )
    assert activate_response.status_code == 200
    body = activate_response.json()
    assert body["is_active"] is True
    assert body["next_run_at"] is not None


@time_machine.travel(FROZEN_TIME, tick=False)
def test_activate_task_idempotent(client, auth_headers_frozen):
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

    first = client.post(
        f"/api/v1/tasks/{task_id}/activate",
        headers=auth_headers_frozen,
    )
    second = client.post(
        f"/api/v1/tasks/{task_id}/activate",
        headers=auth_headers_frozen,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["is_active"] is True


@time_machine.travel(FROZEN_TIME, tick=False)
def test_activate_task_not_found(client, auth_headers_frozen):
    from uuid import uuid4

    response = client.post(
        f"/api/v1/tasks/{uuid4()}/activate",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 404


@time_machine.travel(FROZEN_TIME, tick=False)
def test_activate_task_cross_user_isolation(client, auth_headers_frozen, test_settings):
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
        f"/api/v1/tasks/{task_id}/activate",
        headers=other_headers,
    )
    assert response.status_code == 404


@time_machine.travel(FROZEN_TIME, tick=False)
def test_activate_expired_once_task_returns_422(client, auth_headers_frozen):
    run_at = (FROZEN_TIME - timedelta(hours=1)).isoformat()
    create_response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/hook",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    client.post(
        f"/api/v1/tasks/{task_id}/deactivate",
        headers=auth_headers_frozen,
    )

    response = client.post(
        f"/api/v1/tasks/{task_id}/activate",
        headers=auth_headers_frozen,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Task cannot be activated"


@time_machine.travel(FROZEN_TIME, tick=False)
def test_tasks_cross_user_isolation(client, auth_headers_frozen, test_settings):
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
    assert create_response.status_code == 201

    other_token = jwt.encode(
        {
            "sub": "other-user-456",
            "exp": FROZEN_TIME + timedelta(hours=1),
        },
        test_settings.auth.jwt_secret.get_secret_value(),
        algorithm=test_settings.auth.jwt_algorithm,
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}

    list_response = client.get("/api/v1/tasks", headers=other_headers)
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["total"] == 0
    assert list_body["items"] == []


def test_jwt_encode_decode_round_trip(test_settings):
    token = encode_token(
        test_settings.auth,
        sub="user-abc",
        expires_in=timedelta(minutes=5),
        extra_claims={"task_id": "task-123", "purpose": "webhook"},
    )
    payload = decode_token(token, test_settings.auth)
    assert payload["sub"] == "user-abc"
    assert payload["task_id"] == "task-123"
    assert payload["purpose"] == "webhook"


@time_machine.travel(FROZEN_TIME, tick=False)
def test_executor_calls_webhook(client, run_in_app_loop, test_settings):
    from uuid import uuid4

    from app.scheduler.executor import execute_scheduled_task, init_executor

    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)

    async def _setup_and_run():
        async with httpx.AsyncClient(transport=transport) as http_client:
            factory = client.app.state.session_factory
            scheduler = client.app.state.scheduler
            init_executor(factory, test_settings, http_client, scheduler)

            async with factory() as session:
                await set_scheduler_rls(session)
                task = ScheduledTask(
                    id=uuid4(),
                    user_id=TEST_USER_ID,
                    webhook_url="https://example.com/webhook",
                    parameters={"q": "1"},
                    trigger_type="once",
                    trigger_config={
                        "run_at": (FROZEN_TIME + timedelta(hours=1)).isoformat()
                    },
                    is_active=True,
                )
                session.add(task)
                await session.commit()
                task_id = str(task.id)

            await execute_scheduled_task(task_id)

            async with factory() as session:
                await set_scheduler_rls(session)
                result = await session.execute(
                    select(ScheduledTask).where(ScheduledTask.id == task.id)
                )
                updated = result.scalar_one()
                assert updated.is_active is False

            return task_id

    run_in_app_loop(_setup_and_run)

    assert captured["url"].startswith("https://example.com/webhook")
    assert "q=1" in captured["url"]
    assert captured["authorization"].startswith("Bearer ")

    payload = decode_token(
        captured["authorization"].removeprefix("Bearer "),
        test_settings.auth,
    )
    assert payload["sub"] == TEST_USER_ID
    assert payload["purpose"] == "webhook"
