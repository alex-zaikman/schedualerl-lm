import asyncio
from datetime import timedelta
from uuid import uuid4

import httpx
import jwt
import pytest
import time_machine
from sqlalchemy import text

from app.config.settings import Settings
from tests.constants import FROZEN_TIME, TEST_USER_ID


def _auth_headers(user_id: str, settings: Settings) -> dict[str, str]:
    token = jwt.encode(
        {"sub": user_id, "exp": FROZEN_TIME + timedelta(hours=1)},
        settings.auth.jwt_secret.get_secret_value(),
        algorithm=settings.auth.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def _init_mock_executor(client, test_settings, handler):
    from app.scheduler.executor import init_executor

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


def _create_interval_task(
    client, auth_headers, webhook_url="https://example.com/interval"
):
    return client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "webhook_url": webhook_url,
            "parameters": {},
            "trigger": {"type": "interval", "seconds": 3600},
        },
    )


@time_machine.travel(FROZEN_TIME, tick=False)
def test_create_task_records_task_created(client, auth_headers_frozen):
    response = _create_interval_task(client, auth_headers_frozen)
    assert response.status_code == 201
    task_id = response.json()["id"]

    history = client.get(
        f"/api/v1/tasks/{task_id}/history",
        headers=auth_headers_frozen,
    )
    assert history.status_code == 200
    body = history.json()
    assert body["total"] == 1
    entry = body["items"][0]
    assert entry["event_type"] == "task_created"
    assert entry["webhook_url"] == "https://example.com/interval"
    assert entry["trigger_type"] == "interval"


@time_machine.travel(FROZEN_TIME, tick=False)
def test_activate_deactivate_record_lifecycle(client, auth_headers_frozen):
    create = _create_interval_task(client, auth_headers_frozen)
    task_id = create.json()["id"]

    client.post(f"/api/v1/tasks/{task_id}/deactivate", headers=auth_headers_frozen)
    client.post(f"/api/v1/tasks/{task_id}/activate", headers=auth_headers_frozen)

    history = client.get(
        f"/api/v1/tasks/{task_id}/history?order=asc",
        headers=auth_headers_frozen,
    )
    events = [item["event_type"] for item in history.json()["items"]]
    assert events == ["task_created", "task_deactivated", "task_activated"]


@time_machine.travel(FROZEN_TIME, tick=False)
def test_manual_run_records_execution(client, test_settings, auth_headers_frozen):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    _init_mock_executor(client, test_settings, handler)
    create = _create_interval_task(client, auth_headers_frozen)
    task_id = create.json()["id"]

    run = client.post(f"/api/v1/tasks/{task_id}/run", headers=auth_headers_frozen)
    assert run.status_code == 200

    history = client.get(
        f"/api/v1/tasks/{task_id}/history?event_type=execution",
        headers=auth_headers_frozen,
    )
    entry = history.json()["items"][0]
    assert entry["execution_source"] == "manual"
    assert entry["success"] is True
    assert entry["http_status"] == 200
    assert entry["webhook_url"] == "https://example.com/interval"


@time_machine.travel(FROZEN_TIME, tick=False)
def test_manual_run_failure_records_execution(
    client, test_settings, auth_headers_frozen
):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    _init_mock_executor(client, test_settings, handler)
    create = _create_interval_task(client, auth_headers_frozen)
    task_id = create.json()["id"]

    run = client.post(f"/api/v1/tasks/{task_id}/run", headers=auth_headers_frozen)
    assert run.status_code == 502

    history = client.get(
        f"/api/v1/tasks/{task_id}/history?event_type=execution",
        headers=auth_headers_frozen,
    )
    entry = history.json()["items"][0]
    assert entry["success"] is False
    assert entry["http_status"] == 502
    assert entry["error_message"] is not None


@time_machine.travel(FROZEN_TIME, tick=False)
def test_delete_preserves_history(client, auth_headers_frozen):
    create = _create_interval_task(client, auth_headers_frozen)
    task_id = create.json()["id"]

    delete = client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers_frozen)
    assert delete.status_code == 204

    tasks = client.get("/api/v1/tasks?active_only=false", headers=auth_headers_frozen)
    assert all(item["id"] != task_id for item in tasks.json()["items"])

    history = client.get(
        f"/api/v1/tasks/{task_id}/history?order=desc",
        headers=auth_headers_frozen,
    )
    assert history.status_code == 200
    events = [item["event_type"] for item in history.json()["items"]]
    assert events[0] == "task_deleted"
    assert "task_created" in events


@time_machine.travel(FROZEN_TIME, tick=False)
def test_history_filters(client, auth_headers_frozen):
    create = _create_interval_task(client, auth_headers_frozen)
    task_id = create.json()["id"]

    all_history = client.get("/api/v1/history", headers=auth_headers_frozen)
    assert all_history.status_code == 200

    filtered = client.get(
        f"/api/v1/history?task_id={task_id}&event_type=task_created",
        headers=auth_headers_frozen,
    )
    body = filtered.json()
    assert body["total"] == 1
    assert body["items"][0]["event_type"] == "task_created"


@time_machine.travel(FROZEN_TIME, tick=False)
def test_history_rls_isolation(client, test_settings, auth_headers_frozen):
    create = _create_interval_task(client, auth_headers_frozen)
    task_id = create.json()["id"]

    other_headers = _auth_headers("other-user", test_settings)
    history = client.get(f"/api/v1/tasks/{task_id}/history", headers=other_headers)
    assert history.status_code == 200
    assert history.json()["total"] == 0


@time_machine.travel(FROZEN_TIME, tick=False)
def test_history_is_append_only(client, run_in_app_loop):
    async def _attempt_mutation():
        from app.db.rls import set_scheduler_rls

        session_factory = client.app.state.session_factory
        async with session_factory() as session:
            await set_scheduler_rls(session)
            entry_id = uuid4()
            await session.execute(
                text(
                    """
                    INSERT INTO task_history (
                        id, user_id, task_id, event_type, webhook_url,
                        trigger_type, interval_seconds
                    ) VALUES (
                        :id, :user_id, :task_id, 'task_created', 'https://example.com',
                        'interval', 60
                    )
                    """
                ),
                {
                    "id": entry_id,
                    "user_id": TEST_USER_ID,
                    "task_id": uuid4(),
                },
            )
            await session.commit()
            with pytest.raises(Exception, match="append-only"):
                await session.execute(
                    text("UPDATE task_history SET webhook_url = 'x' WHERE id = :id"),
                    {"id": entry_id},
                )
                await session.commit()

    run_in_app_loop(_attempt_mutation)


async def _wait_for_interval_fires(
    frozen_time, fire_count_ref, expected: int = 3
) -> None:
    for i in range(expected):
        frozen_time.move_to(FROZEN_TIME + timedelta(seconds=2 * (i + 1) + 1))
        for _ in range(200):
            if fire_count_ref["count"] >= i + 1:
                break
            await asyncio.sleep(0.05)
        else:
            raise AssertionError(f"fire {i + 1} did not occur")


def test_scheduled_executions_recorded_in_history(  # pylint: disable=too-many-locals
    client, run_in_app_loop, test_settings, auth_headers_frozen, frozen_time
):
    fire_count_ref = {"count": 0}

    async def handler(_request: httpx.Request) -> httpx.Response:
        fire_count_ref["count"] += 1
        return httpx.Response(200)

    _init_mock_executor(client, test_settings, handler)

    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/interval",
            "parameters": {},
            "trigger": {"type": "interval", "seconds": 2},
        },
    )
    assert response.status_code == 201
    task_id = response.json()["id"]

    async def _wait():
        await _wait_for_interval_fires(frozen_time, fire_count_ref)

    run_in_app_loop(_wait)
    assert fire_count_ref["count"] == 3

    executions = client.get(
        f"/api/v1/tasks/{task_id}/history?event_type=execution&order=asc",
        headers=auth_headers_frozen,
    )
    body = executions.json()
    assert body["total"] == 3
    for entry in body["items"]:
        assert entry["event_type"] == "execution"
        assert entry["execution_source"] == "scheduled"
        assert entry["success"] is True
        assert entry["http_status"] == 200
        assert entry["webhook_url"] == "https://example.com/interval"
        assert entry["error_message"] is None

    all_history = client.get(
        f"/api/v1/tasks/{task_id}/history?order=desc",
        headers=auth_headers_frozen,
    )
    assert all_history.json()["total"] == 4

    second_created_at = body["items"][1]["created_at"]
    window = client.get(
        f"/api/v1/tasks/{task_id}/history"
        f"?event_type=execution&since={second_created_at}&until={second_created_at}",
        headers=auth_headers_frozen,
    )
    assert window.json()["total"] == 1
