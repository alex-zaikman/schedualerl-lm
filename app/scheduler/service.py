import logging
from uuid import UUID

from apscheduler import AsyncScheduler, ConflictPolicy
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from apscheduler.eventbrokers.asyncpg import AsyncpgEventBroker
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config.settings import DatabaseSettings, Settings
from app.db.models.scheduled_task import ScheduledTask
from app.scheduler.executor import (
    WEBHOOK_EXECUTOR_TASK_ID,
    execute_scheduled_task,
    init_executor,
)
from app.scheduler.triggers import build_trigger_from_task

logger = logging.getLogger(__name__)


def _asyncpg_dsn(db: DatabaseSettings) -> str:
    pwd = db.password.get_secret_value()
    return f"postgresql://{db.user}:{pwd}@{db.host}:{db.port}/{db.name}"


def create_scheduler(engine: AsyncEngine, settings: Settings) -> AsyncScheduler:
    data_store = SQLAlchemyDataStore(engine)
    event_broker = AsyncpgEventBroker(_asyncpg_dsn(settings.db))
    kwargs: dict = {}
    if settings.scheduler.scheduler_id is not None:
        kwargs["identity"] = settings.scheduler.scheduler_id
    return AsyncScheduler(data_store, event_broker, **kwargs)


async def configure_scheduler(
    scheduler: AsyncScheduler,
    session_factory,
    settings: Settings,
    http_client,
) -> None:
    init_executor(session_factory, settings, http_client, scheduler)
    await scheduler.configure_task(
        WEBHOOK_EXECUTOR_TASK_ID,
        func=execute_scheduled_task,
    )


async def register_schedule(scheduler: AsyncScheduler, task: ScheduledTask) -> None:
    try:
        trigger = build_trigger_from_task(task)
        await scheduler.add_schedule(
            WEBHOOK_EXECUTOR_TASK_ID,
            trigger,
            id=str(task.id),
            args=[str(task.id)],
            conflict_policy=ConflictPolicy.replace,
        )
    except Exception:
        logger.exception("Failed to register schedule for task %s", task.id)
        raise


async def unregister_schedule(scheduler: AsyncScheduler, task_id: UUID) -> None:
    try:
        await scheduler.remove_schedule(str(task_id))
    except Exception:
        logger.exception("Failed to unregister schedule for task %s", task_id)
        raise


async def register_schedule_by_id(scheduler: AsyncScheduler, session_factory, task_id: UUID) -> None:
    from sqlalchemy import select

    from app.db.rls import set_scheduler_rls

    async with session_factory() as session:
        await set_scheduler_rls(session)
        result = await session.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))
        task = result.scalar_one_or_none()
    if task is None:
        logger.warning("Cannot register schedule: task %s not found", task_id)
        return
    await register_schedule(scheduler, task)
