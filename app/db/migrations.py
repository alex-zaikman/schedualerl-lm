import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generator

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.config.settings import DatabaseSettings

_db_settings_override: ContextVar[DatabaseSettings | None] = ContextVar(
    "db_settings_override", default=None
)


def get_db_settings_override() -> DatabaseSettings | None:
    return _db_settings_override.get()


@contextmanager
def use_db_settings(db: DatabaseSettings) -> Generator[None, None, None]:
    token = _db_settings_override.set(db)
    try:
        yield
    finally:
        _db_settings_override.reset(token)


async def get_current_revision(async_url: str) -> str | None:
    engine = create_async_engine(async_url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as conn:

            def _get_revision(sync_conn) -> str | None:
                context = MigrationContext.configure(sync_conn)
                return context.get_current_revision()

            return await conn.run_sync(_get_revision)
    finally:
        await engine.dispose()


def _alembic_config() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    return cfg


@contextmanager
def run_migrations(db: DatabaseSettings) -> Generator[None, None, None]:
    cfg = _alembic_config()
    with use_db_settings(db):
        command.upgrade(cfg, "head")

    head = ScriptDirectory.from_config(cfg).get_current_head()
    current = asyncio.run(get_current_revision(db.async_url))
    if current != head:
        raise AssertionError(f"expected migration at head {head}, got {current}")

    yield
