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
    response.choices[0].message.content = json.dumps(content)
    return response


@time_machine.travel(FROZEN_TIME, tick=False)
@patch("app.services.trigger_parse.completion")
def test_create_task_with_text_trigger(mock_completion, client, auth_headers_frozen):
    mock_completion.return_value = _mock_llm_response(
        {"type": "cron", "expression": "0 9 * * *", "timezone": "UTC"}
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
    tasks = list_response.json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == body["id"]


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
    assert list_response.json() == []


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

    payload = decode_token(captured["authorization"].removeprefix("Bearer "), test_settings.auth)
    assert payload["sub"] == TEST_USER_ID
    assert payload["purpose"] == "webhook"
