from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_user_rls(session: AsyncSession, user_id: str) -> None:
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": user_id},
    )


async def set_scheduler_rls(session: AsyncSession) -> None:
    await session.execute(text("SELECT set_config('app.is_scheduler', 'true', true)"))
