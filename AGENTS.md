# Agent guide for schedulerlm

This document helps LLM agents call the schedulerlm API. For human setup and deployment, see [README.md](README.md).

## Base URL

Default local: `http://localhost:8000`

## Authentication

All `/api/v1` routes require a JWT Bearer token:

```
Authorization: Bearer <token>
```

The token's `sub` claim is the user id. Tasks are scoped to that user.

Mint a dev token:

```bash
uv run python scripts/mint_dev_jwt.py --sub user-123
```

Verify auth:

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/me
```

Expected response:

```json
{"user_id": "user-123"}
```

## OpenAPI

Machine-readable API contract:

- Schema: `GET /openapi.json`
- Interactive docs: `GET /docs`

Use the OpenAPI schema as the source of truth for request/response shapes.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check (no auth) |
| `GET` | `/api/v1/me` | Verify auth; get user id |
| `POST` | `/api/v1/tasks` | Create a scheduled task |
| `GET` | `/api/v1/tasks` | List tasks |
| `POST` | `/api/v1/tasks/{task_id}/activate` | Resume a paused task |
| `POST` | `/api/v1/tasks/{task_id}/deactivate` | Pause a task |
| `POST` | `/api/v1/triggers/parse` | Parse natural-language schedule text |

## Trigger types

When creating a task (`POST /api/v1/tasks`), set `trigger` to one of:

| type | When to use | Example |
|------|-------------|---------|
| `text` | Natural language schedule | `{"type": "text", "text": "every day at 9am", "timezone": "UTC"}` |
| `cron` | Exact cron expression | `{"type": "cron", "expression": "0 9 * * *", "timezone": "UTC"}` |
| `interval` | Fixed repeat interval | `{"type": "interval", "seconds": 3600}` |
| `once` | Single run at a datetime | `{"type": "once", "run_at": "2026-06-01T09:00:00+00:00"}` |

**Prefer `text`** when the user describes a schedule in plain language. Use structured types when the schedule is already known.

`timezone` must be a valid IANA name (e.g. `UTC`, `America/New_York`).

`once` tasks deactivate after firing. `cron` and `interval` tasks repeat until deactivated.

## Workflows

### Schedule a webhook every day at 9am

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_url": "https://example.com/hook",
    "parameters": {"source": "schedulerlm"},
    "trigger": {
      "type": "text",
      "text": "every day at 9am",
      "timezone": "UTC"
    }
  }'
```

### Preview a schedule before creating a task

```bash
curl -X POST http://localhost:8000/api/v1/triggers/parse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "every day at 9am", "timezone": "UTC"}'
```

Returns `trigger_type`, `trigger_config`, and `next_run_at` without creating a task.

### List active tasks

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/tasks?active_only=true&limit=50&offset=0"
```

Response shape:

```json
{
  "items": [...],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### Pause a task

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/tasks/{task_id}/deactivate"
```

### Resume a paused task

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/tasks/{task_id}/activate"
```

Returns 422 if the task cannot be scheduled (e.g. an expired `once` task).

## Webhook behavior

When a task fires, the executor sends an HTTP GET to `webhook_url` with:

- `parameters` as query string key/value pairs
- `Authorization: Bearer <short-lived JWT>` (not your API token)

Webhook JWT claims: `sub` (user id), `task_id`, `purpose: "webhook"`, `exp`.

## Error codes

| Status | Meaning |
|--------|---------|
| `401` | Missing or invalid Bearer token |
| `404` | Task not found (or not owned by the user) |
| `422` | Validation or trigger parse failure; see `detail` in the response body |

## Task create request shape

```json
{
  "webhook_url": "https://example.com/hook",
  "parameters": {"key": "value"},
  "trigger": { "...": "see trigger types above" }
}
```
