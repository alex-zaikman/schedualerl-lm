import logging
from uuid import uuid4

from apscheduler import AsyncScheduler
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import CurrentUser
from app.auth.dependencies import get_current_user
from app.db.dependencies import get_db
from app.db.models.scheduled_task import ScheduledTask
from app.scheduler.dependencies import get_scheduler
from app.scheduler.service import register_schedule
from app.scheduler.triggers import compute_next_run_at, trigger_config_from_spec
from app.schemas.tasks import TaskCreate, TaskListQuery, TaskListResponse, TaskResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])


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


@router.post("/tasks", status_code=201, response_model=TaskResponse)
async def create_task(
    body: TaskCreate,
    background_tasks: BackgroundTasks,
    scheduler: AsyncScheduler = Depends(get_scheduler),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TaskResponse:
    trigger_type = body.trigger.type
    trigger_config = trigger_config_from_spec(body.trigger)
    next_run_at = compute_next_run_at(body.trigger)

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


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    query: TaskListQuery = Depends(),
    session: AsyncSession = Depends(get_db),
) -> TaskListResponse:
    stmt = select(ScheduledTask).order_by(ScheduledTask.created_at.desc())
    if query.active_only:
        stmt = stmt.where(ScheduledTask.is_active.is_(True))
    result = await session.execute(stmt)
    tasks = result.scalars().all()
    return TaskListResponse([_to_response(task) for task in tasks])
