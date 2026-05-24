import logging
from datetime import timedelta
from uuid import UUID

import httpx
from apscheduler import AsyncScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import encode_token
from app.config.settings import Settings
from app.db.models.scheduled_task import ScheduledTask
from app.db.rls import set_scheduler_rls
from app.db.session import SessionFactory
from app.enums import TriggerType

logger = logging.getLogger(__name__)

WEBHOOK_EXECUTOR_TASK_ID = "webhook_executor"

_session_factory: SessionFactory | None = None
_settings: Settings | None = None
_http_client: httpx.AsyncClient | None = None
_scheduler: AsyncScheduler | None = None


def init_executor(
    session_factory: SessionFactory,
    settings: Settings,
    http_client: httpx.AsyncClient,
    scheduler: AsyncScheduler,
) -> None:
    global _session_factory, _settings, _http_client, _scheduler
    _session_factory = session_factory
    _settings = settings
    _http_client = http_client
    _scheduler = scheduler


def _require_executor() -> tuple[Settings, httpx.AsyncClient]:
    if _settings is None or _http_client is None:
        raise RuntimeError("Scheduler executor not initialized")
    return _settings, _http_client


async def fire_task_webhook(task: ScheduledTask) -> int:
    """Send the webhook GET for a task and return the HTTP status code."""
    settings, http_client = _require_executor()
    token = encode_token(
        settings.auth,
        sub=task.user_id,
        expires_in=timedelta(minutes=settings.scheduler.webhook_jwt_ttl_minutes),
        extra_claims={"task_id": str(task.id), "purpose": "webhook"},
    )
    response = await http_client.get(
        task.webhook_url,
        params=task.parameters,
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return response.status_code


async def execute_scheduled_task(task_id: str) -> None:
    """Run a scheduled webhook GET with a short-lived JWT for the owning user."""
    if _session_factory is None:
        raise RuntimeError("Scheduler executor not initialized")

    async with _session_factory() as session:
        await set_scheduler_rls(session)
        task = await _load_task(session, task_id)
        if task is None:
            logger.warning("Scheduled task %s not found", task_id)
            return
        if not task.is_active:
            logger.info("Scheduled task %s is inactive, skipping", task_id)
            return

        await fire_task_webhook(task)

        if task.trigger_type == TriggerType.ONCE:
            task.is_active = False
            task.next_run_at = None
        await session.commit()

    if task.trigger_type == TriggerType.ONCE and _scheduler is not None:
        await _scheduler.remove_schedule(str(task.id))


async def run_task_manually(task_id: str) -> int:
    """Fire a task webhook immediately without changing task state."""
    if _session_factory is None:
        raise RuntimeError("Scheduler executor not initialized")

    async with _session_factory() as session:
        await set_scheduler_rls(session)
        task = await _load_task(session, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        return await fire_task_webhook(task)


async def _load_task(session: AsyncSession, task_id: str) -> ScheduledTask | None:
    try:
        task_uuid = UUID(task_id)
    except ValueError:
        return None
    result = await session.execute(select(ScheduledTask).where(ScheduledTask.id == task_uuid))
    return result.scalar_one_or_none()
