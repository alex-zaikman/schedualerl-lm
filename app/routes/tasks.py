import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from apscheduler import AsyncScheduler
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import CurrentUser
from app.auth.dependencies import get_current_user
from app.config.dependencies import get_app_settings
from app.config.settings import Settings
from app.db.dependencies import get_db
from app.db.models.scheduled_task import ScheduledTask
from app.enums import TriggerType
from app.scheduler.dependencies import get_scheduler
from app.scheduler.service import register_schedule, unregister_schedule
from app.scheduler.triggers import (
    compute_next_run_at,
    compute_next_run_at_for_task,
    trigger_config_from_spec,
)
from app.schemas.tasks import TaskCreate, TaskListQuery, TaskListResponse, TaskResponse
from app.services.trigger_parse import TriggerParseError, resolve_trigger_spec

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])


async def _get_task_or_404(session: AsyncSession, task_id: UUID) -> ScheduledTask:
    result = await session.execute(
        select(ScheduledTask).where(ScheduledTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _to_response(task: ScheduledTask) -> TaskResponse:
    return TaskResponse(
        id=str(task.id),
        user_id=task.user_id,
        webhook_url=task.webhook_url,
        parameters=task.parameters,
        trigger_type=task.trigger_type,
        trigger_config=task.trigger_config,
        next_run_at=task.next_run_at,
        is_active=task.is_active,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.post(
    "/tasks",
    status_code=201,
    response_model=TaskResponse,
    summary="Create a scheduled task",
    description=(
        "Creates a task that fires an HTTP GET to `webhook_url` on the given schedule. "
        "Prefer `trigger.type: \"text\"` for natural language (e.g. 'every day at 9am'); "
        "use structured types (`once`, `cron`, `interval`) when the schedule is exact. "
        "`once` tasks deactivate after firing; `cron` and `interval` tasks repeat until deactivated."
    ),
)
async def create_task(
    body: TaskCreate,
    background_tasks: BackgroundTasks,
    scheduler: AsyncScheduler = Depends(get_scheduler),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TaskResponse:
    try:
        trigger = resolve_trigger_spec(body.trigger, settings.llm)
    except TriggerParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    trigger_type = trigger.type
    trigger_config = trigger_config_from_spec(trigger)
    next_run_at = compute_next_run_at(trigger)

    task = ScheduledTask(
        id=uuid4(),
        user_id=user.user_id,
        webhook_url=str(body.webhook_url),
        parameters=body.parameters,
        trigger_type=trigger_type,
        trigger_config=trigger_config.model_dump(),
        next_run_at=next_run_at,
        is_active=True,
    )
    session.add(task)
    await session.flush()
    await session.refresh(task)

    background_tasks.add_task(register_schedule, scheduler, task)

    return _to_response(task)


@router.get(
    "/tasks",
    response_model=TaskListResponse,
    summary="List scheduled tasks",
    description=(
        "Returns paginated tasks owned by the authenticated user. "
        "By default only active tasks are returned (`active_only=true`). "
        "Use `limit` and `offset` for pagination."
    ),
)
async def list_tasks(
    query: TaskListQuery = Depends(),
    session: AsyncSession = Depends(get_db),
) -> TaskListResponse:
    filters = []
    if query.active_only:
        filters.append(ScheduledTask.is_active.is_(True))

    count_stmt = select(func.count(ScheduledTask.id))  # pylint: disable=not-callable
    for condition in filters:
        count_stmt = count_stmt.where(condition)
    total = await session.scalar(count_stmt) or 0

    stmt = select(ScheduledTask).order_by(ScheduledTask.created_at.desc())
    for condition in filters:
        stmt = stmt.where(condition)
    stmt = stmt.limit(query.limit).offset(query.offset)
    result = await session.execute(stmt)
    tasks = result.scalars().all()
    return TaskListResponse(
        items=[_to_response(task) for task in tasks],
        total=total,
        limit=query.limit,
        offset=query.offset,
    )


@router.post(
    "/tasks/{task_id}/deactivate",
    response_model=TaskResponse,
    summary="Pause a scheduled task",
    description=(
        "Deactivates a task and removes it from the scheduler. "
        "The task row is retained and can be resumed with activate."
    ),
)
async def deactivate_task(
    task_id: UUID,
    background_tasks: BackgroundTasks,
    scheduler: AsyncScheduler = Depends(get_scheduler),
    session: AsyncSession = Depends(get_db),
) -> TaskResponse:
    task = await _get_task_or_404(session, task_id)

    if task.is_active:
        task.is_active = False
        task.next_run_at = None
        background_tasks.add_task(unregister_schedule, scheduler, task_id)

    return _to_response(task)


@router.post(
    "/tasks/{task_id}/activate",
    response_model=TaskResponse,
    summary="Resume a paused task",
    description=(
        "Reactivates a deactivated task and recomputes `next_run_at` from the stored trigger. "
        "Returns 422 if the task cannot be scheduled (e.g. an expired `once` task)."
    ),
)
async def activate_task(
    task_id: UUID,
    background_tasks: BackgroundTasks,
    scheduler: AsyncScheduler = Depends(get_scheduler),
    session: AsyncSession = Depends(get_db),
) -> TaskResponse:
    task = await _get_task_or_404(session, task_id)

    if task.is_active:
        return _to_response(task)

    next_run_at = compute_next_run_at_for_task(task)
    if next_run_at is None or (
        task.trigger_type == TriggerType.ONCE
        and next_run_at <= datetime.now(timezone.utc)
    ):
        raise HTTPException(status_code=422, detail="Task cannot be activated")

    task.is_active = True
    task.next_run_at = next_run_at
    background_tasks.add_task(register_schedule, scheduler, task)

    return _to_response(task)
