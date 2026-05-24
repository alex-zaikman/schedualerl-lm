import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app


@pytest.fixture
def app(migrated_db: Settings):
    return create_app(migrated_db)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def run_in_app_loop(client: TestClient):
    def _run(awaitable):
        return client.portal.call(awaitable)

    return _run
