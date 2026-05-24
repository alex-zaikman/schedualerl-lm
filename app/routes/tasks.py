import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from apscheduler import AsyncScheduler
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import CurrentUser
from app.auth.dependencies import get_current_user
from app.config.dependencies import get_app_settings
from app.config.settings import Settings
from app.db.dependencies import get_db
from app.db.models.scheduled_task import ScheduledTask
from app.enums import (
    ExecutionSource,
    SortOrder,
    TaskHistoryEventType,
    TaskSortField,
    TriggerType,
)
from app.scheduler.dependencies import get_scheduler
from app.scheduler.executor import run_task_manually
from app.scheduler.service import register_schedule, unregister_schedule
from app.scheduler.triggers import (
    compute_next_run_at,
    compute_next_run_at_for_task,
    compute_upcoming_run_times,
    trigger_config_from_spec,
)
from app.schemas.execution import webhook_fire_result
from app.schemas.tasks import (
    TaskCreate,
    TaskListQuery,
    TaskListResponse,
    TaskResponse,
    TaskRunResponse,
    TaskScheduleQuery,
    TaskScheduleResponse,
)
from app.services.task_history import (
    record_execution,
    record_task_created,
    record_task_deleted,
    record_task_lifecycle,
)
from app.services.trigger_parse import TriggerParseError, resolve_trigger_spec

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])


async def _get_task_or_404(session: AsyncSession, task_id: UUID) -> ScheduledTask:
    result = await session.execute(
        select(ScheduledTask).where(ScheduledTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
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


def _list_order_by(query: TaskListQuery):
    sort_columns = {
        TaskSortField.CREATED_AT: ScheduledTask.created_at,
        TaskSortField.NEXT_RUN_AT: ScheduledTask.next_run_at,
        TaskSortField.UPDATED_AT: ScheduledTask.updated_at,
    }
    column = sort_columns[query.sort]
    ordering = column.asc() if query.order == SortOrder.ASC else column.desc()
    if query.sort == TaskSortField.NEXT_RUN_AT:
        ordering = ordering.nulls_last()
    return ordering


@router.post(
    "/tasks",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskResponse,
    summary="Create a scheduled task",
    description=(
        "Creates a task that fires an HTTP GET to `webhook_url` on the given schedule. "
        "Prefer `trigger.type: \"text\"` for natural language "
        "(e.g. 'every day at 9am'); "
        "use structured types (`once`, `cron`, `interval`) when the schedule is exact. "
        "`once` tasks deactivate after firing; `cron` and `interval` tasks "
        "repeat until deactivated."
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

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

    await record_task_created(session, user_id=user.user_id, task=task)

    background_tasks.add_task(register_schedule, scheduler, task)

    return _to_response(task)


@router.get(
    "/tasks",
    response_model=TaskListResponse,
    summary="List scheduled tasks",
    description=(
        "Returns paginated tasks owned by the authenticated user. "
        "By default only active tasks are returned (`active_only=true`). "
        "Filter by `trigger_type`, sort with `sort` and `order`, "
        "and use `limit` and `offset` for pagination."
    ),
)
async def list_tasks(
    query: TaskListQuery = Depends(),
    session: AsyncSession = Depends(get_db),
) -> TaskListResponse:
    filters = []
    if query.active_only:
        filters.append(ScheduledTask.is_active.is_(True))
    if query.trigger_type is not None:
        filters.append(ScheduledTask.trigger_type == query.trigger_type)

    count_stmt = select(func.count(ScheduledTask.id))  # pylint: disable=not-callable
    for condition in filters:
        count_stmt = count_stmt.where(condition)
    total = await session.scalar(count_stmt) or 0

    stmt = select(ScheduledTask).order_by(_list_order_by(query))
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


@router.get(
    "/tasks/{task_id}/schedule",
    response_model=TaskScheduleResponse,
    summary="Preview upcoming fire times",
    description=(
        "Returns up to `count` future fire times computed from the task's "
        "stored trigger. Works for active and paused tasks; does not mutate the task."
    ),
)
async def get_task_schedule(
    task_id: UUID,
    query: TaskScheduleQuery = Depends(),
    session: AsyncSession = Depends(get_db),
) -> TaskScheduleResponse:
    task = await _get_task_or_404(session, task_id)
    upcoming = compute_upcoming_run_times(task, count=query.count)
    return TaskScheduleResponse(
        trigger_type=task.trigger_type,
        is_active=task.is_active,
        next_run_at=upcoming[0] if upcoming else None,
        upcoming=upcoming,
    )


@router.post(
    "/tasks/{task_id}/run",
    response_model=TaskRunResponse,
    summary="Run a task webhook immediately",
    description=(
        "Fires the task webhook now for testing or debugging. "
        "Works on paused tasks. Does not deactivate `once` tasks or "
        "change `next_run_at`; the scheduled run still occurs at `run_at`."
    ),
)
async def run_task(
    task_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> TaskRunResponse:
    task = await _get_task_or_404(session, task_id)
    user_id = session.info.get("current_user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing user context",
        )

    outcome = await run_task_manually(str(task.id))
    fire_result = webhook_fire_result(
        execution_source=ExecutionSource.MANUAL,
        webhook_url=task.webhook_url,
        outcome=outcome,
    )
    await record_execution(
        session,
        user_id=user_id,
        task_id=task.id,
        execution_source=fire_result.execution_source,
        webhook_url=fire_result.webhook_url,
        success=fire_result.success,
        http_status=fire_result.http_status,
        error_message=fire_result.error_message,
    )
    await session.commit()

    if not fire_result.success:
        if fire_result.http_status is not None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Webhook returned {fire_result.http_status}",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=fire_result.error_message or "Webhook request failed",
        )
    return TaskRunResponse(
        task_id=str(task.id),
        execution_source=fire_result.execution_source,
        webhook_url=fire_result.webhook_url,
        http_status=fire_result.http_status,
        error_message=fire_result.error_message,
        success=fire_result.success,
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
        user_id = session.info.get("current_user_id")
        if user_id is not None:
            await record_task_lifecycle(
                session,
                user_id=user_id,
                task_id=task.id,
                event_type=TaskHistoryEventType.TASK_DEACTIVATED,
            )
        background_tasks.add_task(unregister_schedule, scheduler, task_id)

    return _to_response(task)


@router.post(
    "/tasks/{task_id}/activate",
    response_model=TaskResponse,
    summary="Resume a paused task",
    description=(
        "Reactivates a deactivated task and recomputes `next_run_at` "
        "from the stored trigger. "
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Task cannot be activated",
        )

    task.is_active = True
    task.next_run_at = next_run_at
    user_id = session.info.get("current_user_id")
    if user_id is not None:
        await record_task_lifecycle(
            session,
            user_id=user_id,
            task_id=task.id,
            event_type=TaskHistoryEventType.TASK_ACTIVATED,
        )
    background_tasks.add_task(register_schedule, scheduler, task)

    return _to_response(task)

@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a scheduled task",
    description=(
        "Permanently deletes a task and removes it from the scheduler. "
        "Audit history for the task is retained."
    ),
)
async def delete_task(
    task_id: UUID,
    background_tasks: BackgroundTasks,
    scheduler: AsyncScheduler = Depends(get_scheduler),
    session: AsyncSession = Depends(get_db),
) -> None:
    task = await _get_task_or_404(session, task_id)
    user_id = session.info.get("current_user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing user context",
        )

    if task.is_active:
        background_tasks.add_task(unregister_schedule, scheduler, task_id)

    await record_task_deleted(session, user_id=user_id, task=task)
    await session.delete(task)
