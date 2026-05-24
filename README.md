# schedulerlm

FastAPI service that schedules webhook GET calls. Tasks accept structured triggers (`once`, `cron`, `interval`) or natural-language text parsed by an LLM via LiteLLM. APScheduler persists schedules in PostgreSQL; at fire time the executor calls the webhook with a short-lived JWT for the owning user. API routes are JWT-protected.

For endpoints, auth flows, curl examples, and agent-oriented API usage, see [AGENTS.md](AGENTS.md).

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
