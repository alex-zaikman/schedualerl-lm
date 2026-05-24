import asyncio
from uuid import uuid4

import asyncpg
import pytest
from pydantic import SecretStr
from testcontainers.postgres import PostgresContainer

from app.config.settings import DatabaseSettings, Settings
from app.db.migrations import run_migrations
from tests.fixtures.settings import make_test_settings


@pytest.fixture
def worker_id(request: pytest.FixtureRequest) -> str:
    workerinput = getattr(request.config, "workerinput", None)
    if workerinput is not None:
        return workerinput["workerid"]
    return "master"


@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer:
    try:
        with PostgresContainer("postgres:16-alpine") as postgres:
            yield postgres
    except Exception as exc:
        pytest.skip(f"Docker is required for integration tests: {exc}")


@pytest.fixture
def db_name(worker_id: str) -> str:
    return f"slm_{worker_id}_{uuid4().hex[:8]}"


def container_db_settings(
    container: PostgresContainer,
    db_name: str,
) -> DatabaseSettings:
    return DatabaseSettings(
        host=container.get_container_host_ip(),
        port=int(container.get_exposed_port(5432)),
        user=container.username,
        password=SecretStr(container.password),
        name=db_name,
        min_pool_size=1,
        max_pool_size=2,
        connect_timeout=10.0,
        connect_retries=3,
        connect_retry_delay=1.0,
    )


@pytest.fixture
def test_settings(postgres_container: PostgresContainer, db_name: str) -> Settings:
    return make_test_settings(container_db_settings(postgres_container, db_name))


async def _create_database(admin_db: DatabaseSettings, db_name: str) -> None:
    conn = await asyncpg.connect(
        host=admin_db.host,
        port=admin_db.port,
        user=admin_db.user,
        password=admin_db.password.get_secret_value(),
        database="postgres",
    )
    try:
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


async def _drop_database(admin_db: DatabaseSettings, db_name: str) -> None:
    conn = await asyncpg.connect(
        host=admin_db.host,
        port=admin_db.port,
        user=admin_db.user,
        password=admin_db.password.get_secret_value(),
        database="postgres",
    )
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            db_name,
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    finally:
        await conn.close()


@pytest.fixture
def migrated_db(
    postgres_container: PostgresContainer,
    test_settings: Settings,
    db_name: str,
) -> Settings:
    admin_db = container_db_settings(postgres_container, "postgres")
    asyncio.run(_create_database(admin_db, db_name))
    try:
        with run_migrations(test_settings.db):
            yield test_settings
    finally:
        asyncio.run(_drop_database(admin_db, db_name))
