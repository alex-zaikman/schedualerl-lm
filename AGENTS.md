# Agent guide for schedulerlm

Guide for AI agents **developing** this repo and **calling** its HTTP API. Human setup, deployment, and environment variables: [README.md](README.md).

## Developing this repo

FastAPI service that schedules webhook GET calls via APScheduler with PostgreSQL persistence. Natural-language triggers are parsed with LiteLLM.

### Setup

```bash
cp .env.example .env
uv sync
docker compose up -d db
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

See [README.md](README.md) for the full Docker stack, Ollama, and `.env` configuration.

### Tests and lint

Run before finishing code changes (matches [CI](.github/workflows/ci.yml)):

```bash
uv run pytest
uv run isort --check-only --diff app tests scripts alembic
uv run pylint app tests scripts
```

Integration tests need Docker (testcontainers). Ollama-dependent tests skip if the model is unavailable.

### Code conventions

- **Tenacity:** Use the `@retry` decorator; do not use manual retry loops or imperative `Retrying` / `AsyncRetrying` (see `app/services/trigger_parse.py`, `app/db/engine.py`).
- **Imports:** Never define `__all__`. Import symbols from the module where they are defined, not package barrels or wildcards.
- **Pattern matching:** Prefer `match` / `case` over long `if` / `elif` / `isinstance` chains when dispatching on enums, literals, or typed variants.

## Using the API

### Base URL

Default local: `http://localhost:8000`

### Authentication

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

### OpenAPI

Machine-readable API contract:

- Schema: `GET /openapi.json`
- Interactive docs: `GET /docs`

Use the OpenAPI schema as the source of truth for request/response shapes.

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check (no auth) |
| `GET` | `/api/v1/me` | Verify auth; get user id |
| `POST` | `/api/v1/tasks` | Create a scheduled task |
| `GET` | `/api/v1/tasks` | List tasks (filter, sort, paginate) |
| `GET` | `/api/v1/tasks/{task_id}/schedule` | Preview upcoming fire times |
| `POST` | `/api/v1/tasks/{task_id}/run` | Fire webhook immediately (test/debug) |
| `POST` | `/api/v1/tasks/{task_id}/activate` | Resume a paused task |
| `POST` | `/api/v1/tasks/{task_id}/deactivate` | Pause a task |
| `DELETE` | `/api/v1/tasks/{task_id}` | Delete a task (history retained) |
| `GET` | `/api/v1/history` | List audit history (filter, paginate) |
| `GET` | `/api/v1/tasks/{task_id}/history` | History for one task (works after delete) |
| `POST` | `/api/v1/triggers/parse` | Parse natural-language schedule text |

### Trigger types

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

### Workflows

#### Schedule a webhook every day at 9am

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

#### Preview a schedule before creating a task

```bash
curl -X POST http://localhost:8000/api/v1/triggers/parse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "every day at 9am", "timezone": "UTC"}'
```

Returns `trigger_type`, `trigger_config`, and `next_run_at` without creating a task.

#### List active tasks

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/tasks?active_only=true&limit=50&offset=0"
```

Optional query params: `trigger_type` (`once`, `cron`, `interval`), `sort` (`created_at`, `next_run_at`, `updated_at`), `order` (`asc`, `desc`).

Response shape:

```json
{
  "items": [...],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

#### Preview upcoming fire times for an existing task

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/tasks/{task_id}/schedule?count=5"
```

Returns `trigger_type`, `is_active`, `next_run_at`, and `upcoming` (list of datetimes). Works for active and paused tasks.

#### Run a task webhook immediately

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/tasks/{task_id}/run"
```

Fires the webhook now for testing. Works on paused tasks. Does not deactivate `once` tasks or change `next_run_at`. Returns `502` if the webhook returns a non-2xx status.

Response shape:

```json
{
  "task_id": "...",
  "execution_source": "manual",
  "webhook_url": "https://example.com/hook",
  "http_status": 200,
  "error_message": null,
  "success": true
}
```

#### Pause a task

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/tasks/{task_id}/deactivate"
```

#### Resume a paused task

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/tasks/{task_id}/activate"
```

Returns 422 if the task cannot be scheduled (e.g. an expired `once` task).
#### Query task history

```bash
curl -H "Authorization: Bearer $TOKEN"   "http://localhost:8000/api/v1/history?event_type=execution&limit=50&offset=0"
```

Optional query params: `event_type` (`task_created`, `task_activated`, `task_deactivated`, `task_deleted`, `execution`), `task_id`, `since`, `until`, `order` (`asc`, `desc`).

Each item is typed by `event_type`. Execution entries include `execution_source` (`scheduled` or `manual`), `webhook_url`, `http_status`, `error_message`, and `success`. Skipped scheduled runs (inactive or missing task) are not logged.

#### Query history for a task (including after delete)

```bash
curl -H "Authorization: Bearer $TOKEN"   "http://localhost:8000/api/v1/tasks/{task_id}/history?event_type=execution"
```

Works even when the task row has been deleted. Unknown or other-user task ids return an empty list.

#### Delete a task

```bash
curl -X DELETE   -H "Authorization: Bearer $TOKEN"   "http://localhost:8000/api/v1/tasks/{task_id}"
```

Returns `204`. Records a `task_deleted` event and removes the task from the scheduler. History is retained.


### Webhook behavior

When a task fires, the executor sends an HTTP GET to `webhook_url` with:

- `parameters` as query string key/value pairs
- `Authorization: Bearer <short-lived JWT>` (not your API token)

Webhook JWT claims: `sub` (user id), `task_id`, `purpose: "webhook"`, `exp`.

### Error codes

| Status | Meaning |
|--------|---------|
| `401` | Missing or invalid Bearer token |
| `404` | Task not found (or not owned by the user) |
| `422` | Validation or trigger parse failure; see `detail` in the response body |
| `502` | Manual run webhook failure (non-2xx or connection error) |

### Task create request shape

```json
{
  "webhook_url": "https://example.com/hook",
  "parameters": {"key": "value"},
  "trigger": { "...": "see trigger types above" }
}
```
