from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import HealthStatus
from app.db.dependencies import get_db
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> HealthResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        await session.rollback()
        response.status_code = 503
        return HealthResponse(status=HealthStatus.UNAVAILABLE)
    return HealthResponse(status=HealthStatus.OK)
