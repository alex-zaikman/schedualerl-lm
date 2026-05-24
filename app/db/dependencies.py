from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionFactory


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory: SessionFactory = request.app.state.session_factory
    async with session_factory() as session:
        session.info["current_user_id"] = getattr(request.state, "user_id", None)
        yield session
