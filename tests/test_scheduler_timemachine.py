import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import time_machine

from app.schemas.tasks import CronTriggerSpec, IntervalTriggerSpec, OnceTrigger
from app.scheduler.triggers import build_trigger, compute_next_run_at
from tests.constants import FROZEN_TIME


@time_machine.travel(FROZEN_TIME, tick=False)
def test_cron_next_run_at_same_day():
    next_run = compute_next_run_at(CronTriggerSpec(expression="0 9 * * *", timezone="UTC"))
    assert next_run == datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc)


@time_machine.travel(datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc), tick=False)
def test_cron_next_run_at_next_day_after_missed_hour():
    next_run = compute_next_run_at(CronTriggerSpec(expression="0 9 * * *", timezone="UTC"))
    assert next_run == datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc)


@time_machine.travel(FROZEN_TIME, tick=False)
def test_cron_trigger_advances_with_time_travel():
    trigger = build_trigger(CronTriggerSpec(expression="0 9 * * *", timezone="UTC"))
    first = trigger.next()
    assert first == datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc)

    with time_machine.travel(datetime(2026, 5, 24, 9, 1, tzinfo=timezone.utc), tick=False):
        second = trigger.next()
    assert second == datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc)


@time_machine.travel(FROZEN_TIME, tick=False)
def test_interval_next_run_at():
    next_run = compute_next_run_at(IntervalTriggerSpec(seconds=300))
    assert next_run == FROZEN_TIME


@time_machine.travel(FROZEN_TIME, tick=False)
def test_once_next_run_at():
    run_at = FROZEN_TIME + timedelta(minutes=30)
    next_run = compute_next_run_at(OnceTrigger(run_at=run_at))
    assert next_run == run_at


def test_create_cron_task_via_api(client, auth_headers_frozen, frozen_time):
    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/cron",
            "parameters": {"source": "cron"},
            "trigger": {"type": "cron", "expression": "0 9 * * *", "timezone": "UTC"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["trigger_type"] == "cron"
    assert body["next_run_at"] == "2026-05-24T09:00:00Z"


def test_create_interval_task_via_api(client, auth_headers_frozen, frozen_time):
    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/interval",
            "parameters": {},
            "trigger": {"type": "interval", "seconds": 300},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["trigger_type"] == "interval"
    assert body["next_run_at"] == "2026-05-24T08:00:00Z"


def test_create_once_task_via_api(client, auth_headers_frozen, frozen_time):
    run_at = (FROZEN_TIME + timedelta(minutes=15)).isoformat()
    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/once",
            "parameters": {"x": "1"},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["trigger_type"] == "once"
    assert body["next_run_at"] == "2026-05-24T08:15:00Z"


def test_scheduler_fires_once_task_after_time_travel(
    client, run_in_app_loop, test_settings, auth_headers_frozen, frozen_time
):
    from app.scheduler.executor import init_executor

    captured: dict[str, bool] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["called"] = True
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    init_executor(
        client.app.state.session_factory,
        test_settings,
        http_client,
        client.app.state.scheduler,
    )
    client.app.state._test_http_client = http_client

    run_at = (FROZEN_TIME + timedelta(seconds=2)).isoformat()
    response = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/fire",
            "parameters": {"k": "v"},
            "trigger": {"type": "once", "run_at": run_at},
        },
    )
    assert response.status_code == 201

    async def _wait_for_fire():
        frozen_time.move_to(FROZEN_TIME + timedelta(seconds=5))
        for _ in range(50):
            if captured.get("called"):
                return
            await asyncio.sleep(0.05)
        raise AssertionError("scheduled webhook did not fire")

    run_in_app_loop(_wait_for_fire)
    assert captured["called"]

    async def _close_http_client():
        http_client = getattr(client.app.state, "_test_http_client", None)
        if http_client is not None:
            await http_client.aclose()

    run_in_app_loop(_close_http_client)
