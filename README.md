# schedulerlm

[![CI](https://github.com/alex-zaikman/schedualerl-lm/actions/workflows/ci.yml/badge.svg)](https://github.com/alex-zaikman/schedualerl-lm/actions/workflows/ci.yml)

Schedule webhooks with cron, intervals, or plain English — powered by LiteLLM.

FastAPI service that persists schedules in PostgreSQL (APScheduler), parses natural-language triggers via an LLM, and fires webhook GET calls with a short-lived JWT for the task owner.

## Why schedulerlm

- **Cron is hard** — describe schedules in plain language (`"every day at 9am"`) instead of memorizing cron syntax.
- **Webhook-first** — at fire time the executor calls your URL with query parameters and a scoped JWT; no polling required.
- **Durable** — schedules survive restarts; APScheduler stores state in PostgreSQL with row-level security per user.

## Who it's for

- Automation builders and AI agents scheduling callbacks
- Side projects and internal tools that need reliable timed webhooks
- Teams that want a self-hosted scheduler API without running a full cron-as-a-service platform

Not a fit (yet) if you need a UI dashboard, multi-region HA, or managed SaaS.

## Quick demo

Start the stack (app, Postgres, Ollama for text triggers):

```bash
docker compose up --build
```

Mint a dev JWT, create a task, and list it. Use [webhook.site](https://webhook.site) to inspect fired webhooks (copy your unique URL from the page):

```bash
export TOKEN=$(uv run python scripts/mint_dev_jwt.py --sub user-123)
export WEBHOOK_URL=https://webhook.site/your-unique-id   # from webhook.site

curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"webhook_url\": \"$WEBHOOK_URL\",
    \"parameters\": {\"source\": \"schedulerlm\"},
    \"trigger\": {
      \"type\": \"text\",
      \"text\": \"every day at 9am\",
      \"timezone\": \"UTC\"
    }
  }"

curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/tasks?active_only=true"
```

Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Runnable script: [examples/create_daily_task.sh](examples/create_daily_task.sh) (requires `WEBHOOK_URL` from [webhook.site](https://webhook.site)).

For full endpoint reference, curl examples, and agent-oriented usage, see [AGENTS.md](AGENTS.md).

## Architecture

```text
Client (JWT) → FastAPI → APScheduler (Postgres) → webhook GET + short-lived JWT
                    ↘ LiteLLM (text triggers)
```


| Layer              | Module                                                           |
| ------------------ | ---------------------------------------------------------------- |
| HTTP API           | `[app/routes/tasks.py](app/routes/tasks.py)`                     |
| NL trigger parsing | `[app/services/trigger_parse.py](app/services/trigger_parse.py)` |
| Webhook execution  | `[app/scheduler/executor.py](app/scheduler/executor.py)`         |


## Webhooks

At fire time the executor sends an HTTP GET to the task's `webhook_url` with `parameters` as query params. There is no request body. Non-2xx responses fail the run. Timeout is `SCHEDULER_WEBHOOK_TIMEOUT_SECONDS` (default 30).

Webhook JWT TTL is `SCHEDULER_WEBHOOK_JWT_TTL_MINUTES` (default 5). If your webhook service trusts `AUTH_JWT_SECRET`, it can verify the token and act on behalf of the task creator (`sub` claim). See [AGENTS.md](AGENTS.md#webhook-behavior) for claim details.

## Auth

Routes under `/api/v1` require `Authorization: Bearer <token>`. The middleware validates the JWT with `AUTH_JWT_SECRET` and reads `sub` as the user id. Tasks are scoped to the creator.

The scheduler does not forward your API token on webhook calls; it mints a separate short-lived JWT at fire time.

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

## License

MIT No Attribution — see [LICENSE](LICENSE).
