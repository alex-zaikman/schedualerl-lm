import asyncio
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import time_machine
from sqlalchemy import text

from tests.constants import FROZEN_TIME, TEST_USER_ID


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
def test_history_rls_isolation(client, auth_headers_frozen, other_user_headers_frozen):
    create = _create_interval_task(client, auth_headers_frozen)
    task_id = create.json()["id"]

    history = client.get(
        f"/api/v1/tasks/{task_id}/history", headers=other_user_headers_frozen
    )
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

def test_scheduled_failure_records_execution_and_keeps_task_active(
    client, run_in_app_loop, test_settings, auth_headers_frozen, frozen_time
):
    fire_count_ref = {"count": 0}

    async def handler(_request: httpx.Request) -> httpx.Response:
        fire_count_ref["count"] += 1
        return httpx.Response(502)

    _init_mock_executor(client, test_settings, handler)

    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/fail",
            "parameters": {},
            "trigger": {"type": "interval", "seconds": 2},
        },
    )
    assert response.status_code == 201
    task_id = response.json()["id"]

    async def _wait():
        await _wait_for_interval_fires(frozen_time, fire_count_ref, expected=1)

    run_in_app_loop(_wait)
    assert fire_count_ref["count"] == 1

    executions = client.get(
        f"/api/v1/tasks/{task_id}/history?event_type=execution",
        headers=auth_headers_frozen,
    )
    entry = executions.json()["items"][0]
    assert entry["execution_source"] == "scheduled"
    assert entry["success"] is False
    assert entry["http_status"] == 502

    tasks = client.get("/api/v1/tasks?active_only=true", headers=auth_headers_frozen)
    task = next(item for item in tasks.json()["items"] if item["id"] == task_id)
    assert task["is_active"] is True


def test_inactive_task_does_not_record_scheduled_execution(
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
            "webhook_url": "https://example.com/paused",
            "parameters": {},
            "trigger": {"type": "interval", "seconds": 2},
        },
    )
    assert response.status_code == 201
    task_id = response.json()["id"]

    client.post(f"/api/v1/tasks/{task_id}/deactivate", headers=auth_headers_frozen)

    history_before = client.get(
        f"/api/v1/tasks/{task_id}/history",
        headers=auth_headers_frozen,
    )
    count_before = history_before.json()["total"]
    assert count_before == 2

    async def _wait():
        frozen_time.move_to(FROZEN_TIME + timedelta(seconds=10))
        await asyncio.sleep(0.5)

    run_in_app_loop(_wait)
    assert fire_count_ref["count"] == 0

    history_after = client.get(
        f"/api/v1/tasks/{task_id}/history",
        headers=auth_headers_frozen,
    )
    assert history_after.json()["total"] == count_before
    events = [item["event_type"] for item in history_after.json()["items"]]
    assert "execution" not in events


def test_once_scheduled_fire_records_execution_and_deactivates(  # pylint: disable=too-many-locals
    client, run_in_app_loop, test_settings, auth_headers_frozen, frozen_time
):
    fire_count_ref = {"count": 0}

    async def handler(_request: httpx.Request) -> httpx.Response:
        fire_count_ref["count"] += 1
        return httpx.Response(200)

    _init_mock_executor(client, test_settings, handler)

    run_at = (FROZEN_TIME + timedelta(seconds=2)).isoformat()
    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/once",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    assert response.status_code == 201
    task_id = response.json()["id"]

    async def _wait():
        frozen_time.move_to(FROZEN_TIME + timedelta(seconds=5))
        for _ in range(200):
            if fire_count_ref["count"] >= 1:
                return
            await asyncio.sleep(0.05)
        raise AssertionError("scheduled webhook did not fire")

    run_in_app_loop(_wait)

    executions = client.get(
        f"/api/v1/tasks/{task_id}/history?event_type=execution",
        headers=auth_headers_frozen,
    )
    assert executions.json()["total"] == 1
    entry = executions.json()["items"][0]
    assert entry["execution_source"] == "scheduled"
    assert entry["success"] is True

    events = [
        item["event_type"]
        for item in client.get(
            f"/api/v1/tasks/{task_id}/history?order=asc",
            headers=auth_headers_frozen,
        ).json()["items"]
    ]
    assert events == ["task_created", "execution"]
    assert "task_deactivated" not in events

    tasks = client.get("/api/v1/tasks?active_only=false", headers=auth_headers_frozen)
    task = next(item for item in tasks.json()["items"] if item["id"] == task_id)
    assert task["is_active"] is False


@time_machine.travel(FROZEN_TIME, tick=False)
def test_full_audit_timeline(  # pylint: disable=too-many-locals
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
            "webhook_url": "https://example.com/timeline",
            "parameters": {},
            "trigger": {"type": "interval", "seconds": 2},
        },
    )
    assert response.status_code == 201
    task_id = response.json()["id"]

    async def _wait():
        await _wait_for_interval_fires(frozen_time, fire_count_ref, expected=1)

    run_in_app_loop(_wait)

    run = client.post(f"/api/v1/tasks/{task_id}/run", headers=auth_headers_frozen)
    assert run.status_code == 200

    client.post(f"/api/v1/tasks/{task_id}/deactivate", headers=auth_headers_frozen)
    client.post(f"/api/v1/tasks/{task_id}/activate", headers=auth_headers_frozen)
    delete = client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers_frozen)
    assert delete.status_code == 204

    history = client.get(
        f"/api/v1/tasks/{task_id}/history?order=asc",
        headers=auth_headers_frozen,
    )
    events = [item["event_type"] for item in history.json()["items"]]
    assert events == [
        "task_created",
        "execution",
        "execution",
        "task_deactivated",
        "task_activated",
        "task_deleted",
    ]

    executions = [
        item
        for item in history.json()["items"]
        if item["event_type"] == "execution"
    ]
    assert [item["execution_source"] for item in executions] == [
        "scheduled",
        "manual",
    ]
    for item in executions:
        assert item["webhook_url"] == "https://example.com/timeline"
        assert item["success"] is True


def test_history_multi_tenant_isolation(  # pylint: disable=too-many-locals
    client,
    run_in_app_loop,
    test_settings,
    auth_headers_frozen,
    other_user_headers_frozen,
    frozen_time,
):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    _init_mock_executor(client, test_settings, handler)

    # Once + far-future run_at avoids interval tasks auto-firing before manual runs.
    run_at = (FROZEN_TIME + timedelta(hours=2)).isoformat()
    task_a = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/a",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    assert task_a.status_code == 201
    task_a_id = task_a.json()["id"]

    task_b = client.post(
        "/api/v1/tasks",
        headers=other_user_headers_frozen,
        json={
            "webhook_url": "https://example.com/b",
            "parameters": {},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    assert task_b.status_code == 201
    task_b_id = task_b.json()["id"]

    assert (
        client.post(
            f"/api/v1/tasks/{task_a_id}/run", headers=auth_headers_frozen
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/tasks/{task_b_id}/run", headers=other_user_headers_frozen
        ).status_code
        == 200
    )

    history_a = client.get("/api/v1/history", headers=auth_headers_frozen).json()
    history_b = client.get("/api/v1/history", headers=other_user_headers_frozen).json()
    assert history_a["total"] == 2
    assert history_b["total"] == 2
    assert all(item["task_id"] == task_a_id for item in history_a["items"])
    assert all(item["task_id"] == task_b_id for item in history_b["items"])

    assert (
        client.get(
            f"/api/v1/history?task_id={task_a_id}",
            headers=other_user_headers_frozen,
        ).json()["total"]
        == 0
    )
    assert (
        client.get(
            f"/api/v1/tasks/{task_a_id}/history",
            headers=other_user_headers_frozen,
        ).json()["total"]
        == 0
    )

    fire_count_ref = {"count": 0}

    async def scheduled_handler(_request: httpx.Request) -> httpx.Response:
        fire_count_ref["count"] += 1
        return httpx.Response(200)

    _init_mock_executor(client, test_settings, scheduled_handler)

    scheduled_task = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/a-scheduled",
            "parameters": {},
            "trigger": {"type": "interval", "seconds": 2},
        },
    )
    assert scheduled_task.status_code == 201
    scheduled_task_id = scheduled_task.json()["id"]

    async def _wait():
        await _wait_for_interval_fires(frozen_time, fire_count_ref, expected=1)

    run_in_app_loop(_wait)

    assert (
        client.get(
            f"/api/v1/history?task_id={scheduled_task_id}&event_type=execution",
            headers=auth_headers_frozen,
        ).json()["total"]
        == 1
    )
    assert (
        client.get(
            f"/api/v1/history?task_id={scheduled_task_id}&event_type=execution",
            headers=other_user_headers_frozen,
        ).json()["total"]
        == 0
    )

    assert (
        client.delete(
            f"/api/v1/tasks/{scheduled_task_id}", headers=auth_headers_frozen
        ).status_code
        == 204
    )

    owner_history = client.get(
        f"/api/v1/tasks/{scheduled_task_id}/history?order=asc",
        headers=auth_headers_frozen,
    ).json()
    owner_events = [item["event_type"] for item in owner_history["items"]]
    assert owner_events == ["task_created", "execution", "task_deleted"]

    assert (
        client.get(
            f"/api/v1/tasks/{scheduled_task_id}/history",
            headers=other_user_headers_frozen,
        ).json()["total"]
        == 0
    )
    assert (
        client.get(
            f"/api/v1/history?task_id={scheduled_task_id}",
            headers=other_user_headers_frozen,
        ).json()["total"]
        == 0
    )
