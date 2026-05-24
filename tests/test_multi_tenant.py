import time_machine

from tests.constants import FROZEN_TIME


@time_machine.travel(FROZEN_TIME, tick=False)
def test_cross_api_tenant_boundary(
    client, auth_headers_frozen, other_user_headers_frozen
):
    task_a = client.post(
        "/api/v1/tasks",
        headers=auth_headers_frozen,
        json={
            "webhook_url": "https://example.com/a-cron",
            "parameters": {},
            "trigger": {
                "type": "cron",
                "expression": "0 9 * * *",
                "timezone": "UTC",
            },
        },
    )
    assert task_a.status_code == 201
    task_a_id = task_a.json()["id"]

    task_b = client.post(
        "/api/v1/tasks",
        headers=other_user_headers_frozen,
        json={
            "webhook_url": "https://example.com/b-interval",
            "parameters": {},
            "trigger": {"type": "interval", "seconds": 3600},
        },
    )
    assert task_b.status_code == 201

    for method, path in [
        ("post", f"/api/v1/tasks/{task_a_id}/run"),
        ("post", f"/api/v1/tasks/{task_a_id}/deactivate"),
        ("post", f"/api/v1/tasks/{task_a_id}/activate"),
        ("delete", f"/api/v1/tasks/{task_a_id}"),
    ]:
        response = getattr(client, method)(path, headers=other_user_headers_frozen)
        assert response.status_code == 404

    assert (
        client.get(
            f"/api/v1/tasks/{task_a_id}/schedule",
            headers=other_user_headers_frozen,
        ).status_code
        == 404
    )

    assert (
        client.get(
            "/api/v1/tasks?trigger_type=cron&active_only=false",
            headers=other_user_headers_frozen,
        ).json()["total"]
        == 0
    )
    filtered_a = client.get(
        "/api/v1/tasks?trigger_type=cron&active_only=false",
        headers=auth_headers_frozen,
    ).json()
    assert filtered_a["total"] == 1
    assert filtered_a["items"][0]["id"] == task_a_id

    list_b = client.get(
        "/api/v1/tasks?active_only=false",
        headers=other_user_headers_frozen,
    ).json()
    assert list_b["total"] == 1
    assert list_b["items"][0]["id"] == task_b.json()["id"]

    list_a = client.get("/api/v1/tasks", headers=auth_headers_frozen).json()
    assert list_a["total"] == 1
    assert list_a["items"][0]["id"] == task_a_id
    assert list_a["items"][0]["is_active"] is True

    assert (
        client.get(
            f"/api/v1/tasks/{task_a_id}/schedule",
            headers=auth_headers_frozen,
        ).status_code
        == 200
    )

    history_a = client.get(
        f"/api/v1/tasks/{task_a_id}/history",
        headers=auth_headers_frozen,
    ).json()
    assert history_a["total"] == 1
    assert history_a["items"][0]["event_type"] == "task_created"

    assert (
        client.get(
            f"/api/v1/tasks/{task_a_id}/history",
            headers=other_user_headers_frozen,
        ).json()["total"]
        == 0
    )
    assert (
        client.get(
            f"/api/v1/history?task_id={task_a_id}",
            headers=other_user_headers_frozen,
        ).json()["total"]
        == 0
    )
