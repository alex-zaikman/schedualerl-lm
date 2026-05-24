import logging
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import CurrentUser
from app.auth.dependencies import get_current_user
from app.db.dependencies import get_db
from app.db.models.scheduled_task import ScheduledTask
from app.scheduler.service import register_schedule
from app.scheduler.triggers import compute_next_run_at, trigger_config_from_spec
from app.schemas.tasks import TaskCreate, TaskResponse

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


@router.post("/tasks", status_code=201)
async def create_task(
    body: TaskCreate,
    background_tasks: BackgroundTasks,
    request: Request,
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
        trigger_config=trigger_config,
        next_run_at=next_run_at,
        is_active=True,
    )
    session.add(task)
    await session.flush()
    await session.refresh(task)

    scheduler = request.app.state.scheduler
    background_tasks.add_task(register_schedule, scheduler, task)

    return _to_response(task)


@router.get("/tasks")
async def list_tasks(
    session: AsyncSession = Depends(get_db),
    active_only: bool = Query(default=True),
) -> list[TaskResponse]:
    stmt = select(ScheduledTask).order_by(ScheduledTask.created_at.desc())
    if active_only:
        stmt = stmt.where(ScheduledTask.is_active.is_(True))
    result = await session.execute(stmt)
    tasks = result.scalars().all()
    return [_to_response(task) for task in tasks]
