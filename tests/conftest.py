from unittest.mock import patch

from pydantic import SecretStr

from app.config.settings import DatabaseSettings
from tests.fixtures.settings import make_test_settings

# app.main calls get_settings() at import time; tests inject Settings via fixtures.
patch(
    "app.config.settings.get_settings",
    lambda: make_test_settings(
        DatabaseSettings(
            user="test",
            password=SecretStr("test"),
            name="test",
        )
    ),
).start()

pytest_plugins = [
    "tests.fixtures.db",
    "tests.fixtures.app",
    "tests.fixtures.auth",
    "tests.fixtures.time",
    "tests.fixtures.ollama",
]
