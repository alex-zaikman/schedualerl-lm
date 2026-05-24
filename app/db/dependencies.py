from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import set_user_rls
from app.db.session import SessionFactory


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory: SessionFactory = request.app.state.session_factory
    async with session_factory() as session:
        user_id = getattr(request.state, "user_id", None)
        session.info["current_user_id"] = user_id
        if user_id:
            await set_user_rls(session, user_id)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
