import asyncio
import logging

import asyncpg
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from app.config.settings import DatabaseSettings

logger = logging.getLogger(__name__)


class DatabaseConnectionError(Exception):
    """Raised when a connection cannot be established after all retries."""


def make_async_creator(settings: DatabaseSettings):
    """Factory returning an async_creator callable for create_async_engine."""

    def _raise_connection_error(retry_state) -> None:
        exc = retry_state.outcome.exception()
        raise DatabaseConnectionError(
            f"Failed to connect to PostgreSQL at {settings.host}:{settings.port}/{settings.name}"
        ) from exc

    @retry(
        stop=stop_after_attempt(settings.connect_retries),
        wait=wait_fixed(settings.connect_retry_delay),
        retry=retry_if_exception_type(
            (OSError, asyncio.TimeoutError, asyncpg.PostgresError, SQLAlchemyError)
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        retry_error_callback=_raise_connection_error,
    )
    async def async_creator() -> asyncpg.Connection:
        return await asyncpg.connect(
            host=settings.host,
            port=settings.port,
            user=settings.user,
            password=settings.password.get_secret_value(),
            database=settings.name,
            timeout=settings.connect_timeout,
        )

    return async_creator


async def create_db(
    settings: DatabaseSettings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "postgresql+asyncpg://",
        async_creator=make_async_creator(settings),
        pool_size=settings.min_pool_size,
        max_overflow=max(0, settings.max_pool_size - settings.min_pool_size),
        pool_timeout=settings.connect_timeout,
    )
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    logger.info("PostgreSQL engine ready")
    return engine, session_factory
