from pydantic import SecretStr

from app.config.settings import (
    AppSettings,
    AuthSettings,
    DatabaseSettings,
    LLMSettings,
    LogSettings,
    SchedulerSettings,
    Settings,
)
from tests.constants import (
    TEST_JWT_SECRET,
    TEST_LLM_MAX_RETRIES,
    TEST_LLM_TIMEOUT_SECONDS,
)


def make_test_settings(db: DatabaseSettings) -> Settings:
    return Settings(
        app=AppSettings(name="schedulerlm-test", debug=False),
        auth=AuthSettings(jwt_secret=SecretStr(TEST_JWT_SECRET), jwt_algorithm="HS256"),
        log=LogSettings(level="WARNING"),
        db=db,
        scheduler=SchedulerSettings(
            webhook_jwt_ttl_minutes=5,
            webhook_timeout_seconds=30.0,
        ),
        llm=LLMSettings(
            max_retries=TEST_LLM_MAX_RETRIES,
            timeout_seconds=TEST_LLM_TIMEOUT_SECONDS,
        ),
    )
