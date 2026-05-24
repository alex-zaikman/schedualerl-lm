from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db
from app.db.models.task_history import TaskHistory
from app.enums import SortOrder
from app.schemas.history import HistoryListQuery, HistoryListResponse, entry_from_row

router = APIRouter(tags=["history"])


def _history_order_by(order: SortOrder):
    column = TaskHistory.created_at
    return column.asc() if order == SortOrder.ASC else column.desc()


def _history_filters(query: HistoryListQuery, *, task_id: UUID | None = None) -> list:
    filters = []
    scoped_task_id = task_id if task_id is not None else query.task_id
    if scoped_task_id is not None:
        filters.append(TaskHistory.task_id == scoped_task_id)
    if query.event_type is not None:
        filters.append(TaskHistory.event_type == query.event_type)
    if query.since is not None:
        filters.append(TaskHistory.created_at >= query.since)
    if query.until is not None:
        filters.append(TaskHistory.created_at <= query.until)
    return filters


async def _list_history(
    session: AsyncSession,
    query: HistoryListQuery,
    *,
    task_id: UUID | None = None,
) -> HistoryListResponse:
    filters = _history_filters(query, task_id=task_id)

    count_stmt = select(func.count(TaskHistory.id))  # pylint: disable=not-callable
    for condition in filters:
        count_stmt = count_stmt.where(condition)
    total = await session.scalar(count_stmt) or 0

    stmt = select(TaskHistory).order_by(_history_order_by(query.order))
    for condition in filters:
        stmt = stmt.where(condition)
    stmt = stmt.limit(query.limit).offset(query.offset)
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return HistoryListResponse(
        items=[entry_from_row(row) for row in rows],
        total=total,
        limit=query.limit,
        offset=query.offset,
    )


@router.get(
    "/history",
    response_model=HistoryListResponse,
    summary="List task history",
    description=(
        "Returns paginated audit history for the authenticated user. "
        "Filter by event_type, task_id, and created_at range."
    ),
)
async def list_history(
    query: HistoryListQuery = Depends(),
    session: AsyncSession = Depends(get_db),
) -> HistoryListResponse:
    return await _list_history(session, query)


@router.get(
    "/tasks/{task_id}/history",
    response_model=HistoryListResponse,
    summary="List history for a task",
    description=(
        "Returns paginated history for a task. Works even after the task is deleted."
    ),
)
async def list_task_history(
    task_id: UUID,
    query: HistoryListQuery = Depends(),
    session: AsyncSession = Depends(get_db),
) -> HistoryListResponse:
    return await _list_history(session, query, task_id=task_id)
