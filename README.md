# schedulerlm

FastAPI service that schedules webhook GET calls. Tasks accept structured triggers (`once`, `cron`, `interval`) or natural-language text parsed by an LLM via LiteLLM. APScheduler persists schedules in PostgreSQL; at fire time the executor calls the webhook with a short-lived JWT for the owning user. API routes are JWT-protected.

For LLM agent usage, see [AGENTS.md](AGENTS.md).

Endpoints:

- `GET /health`
- `GET /api/v1/me`
- `POST /api/v1/tasks` — create a scheduled task
- `GET /api/v1/tasks` — list tasks (`active_only`, `limit`, `offset`)
- `POST /api/v1/tasks/{task_id}/activate` — resume a deactivated task
- `POST /api/v1/tasks/{task_id}/deactivate` — pause a task
- `POST /api/v1/triggers/parse` — parse natural-language schedule text

## Webhooks

Creating a task stores a `webhook_url`, optional `parameters` (query string), and a trigger. At fire time the executor sends an HTTP GET to that URL with `parameters` as query params. There is no request body. Non-2xx responses fail the run. Timeout is `SCHEDULER_WEBHOOK_TIMEOUT_SECONDS` (default 30).

`once` tasks deactivate and are removed from the scheduler after they fire. `cron` and `interval` tasks keep running until deactivated.

Use `POST /api/v1/tasks/{task_id}/deactivate` to pause a task and `POST /api/v1/tasks/{task_id}/activate` to resume it. Activation recomputes `next_run_at` from the stored trigger; expired `once` tasks (past `run_at`) return 422.

`GET /api/v1/tasks` returns paginated results: `{ "items": [...], "total": N, "limit": 50, "offset": 0 }`. Query params: `active_only` (default `true`), `limit` (1–100, default 50), `offset` (default 0).

## Auth

**API calls.** Routes under `/api/v1` require `Authorization: Bearer <token>`. The middleware validates the JWT with `AUTH_JWT_SECRET` and reads `sub` as the user id. Task creation stores that user id on the row; tasks are scoped to the creator.

**Webhook calls.** The scheduler does not forward your API token. At fire time it mints a new short-lived JWT signed with the same secret and sends it as `Authorization: Bearer <token>` on the GET to your webhook.

Webhook JWT claims:

- `sub` — user id of the task creator
- `task_id` — scheduled task UUID
- `purpose` — `"webhook"`
- `exp` — `SCHEDULER_WEBHOOK_JWT_TTL_MINUTES` (default 5)

If your webhook service trusts `AUTH_JWT_SECRET`, it can verify the token and act on behalf of `sub`.

## Requirements

- Python 3.12–3.13
- [uv](https://docs.astral.sh/uv/) for dependencies
- Docker (Postgres via compose; testcontainers in pytest)

Optional for LLM features: Ollama with model `ollama/llama3.2` (see [.env.example](.env.example)).

## Local setup

```bash
cp .env.example .env
uv sync
docker compose up -d db
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Mint a dev JWT for API calls:

```bash
uv run python scripts/mint_dev_jwt.py --sub user-123
# Authorization: Bearer <token>
```

Full stack (app, Postgres, Ollama):

```bash
docker compose up --build
```

Compose runs migrations and starts uvicorn via [scripts/docker-entrypoint.sh](scripts/docker-entrypoint.sh).

Smoke checks:

```bash
curl http://localhost:8000/health
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/me
```

## Pytest

```bash
uv sync
uv run pytest
uv run pytest tests/test_tasks.py
uv run pytest -k "cron"
```

Integration tests use testcontainers to start Postgres — Docker must be running.

Tests in `test_trigger_parse_ollama.py` and `test_tasks_ollama.py` require Ollama at `LLM_API_BASE` with the configured model; they skip if unavailable.

Config: `asyncio_mode = auto`, test path `tests/` (see [pyproject.toml](pyproject.toml)).

## Linting

Config: isort and pylint in [pyproject.toml](pyproject.toml).

```bash
uv sync
uv run isort --check-only --diff app tests scripts alembic  # check import order
uv run isort app tests scripts alembic                      # fix import order
uv run pylint app tests scripts
```
