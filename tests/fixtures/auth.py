from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config.settings import Settings
from tests.constants import FROZEN_TIME, OTHER_USER_ID, TEST_USER_ID


@pytest.fixture
def auth_headers_frozen(test_settings: Settings) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": TEST_USER_ID,
            "exp": FROZEN_TIME + timedelta(hours=1),
        },
        test_settings.auth.jwt_secret.get_secret_value(),
        algorithm=test_settings.auth.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers(test_settings: Settings) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": TEST_USER_ID,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        test_settings.auth.jwt_secret.get_secret_value(),
        algorithm=test_settings.auth.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_user_headers_frozen(test_settings: Settings) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": OTHER_USER_ID,
            "exp": FROZEN_TIME + timedelta(hours=1),
        },
        test_settings.auth.jwt_secret.get_secret_value(),
        algorithm=test_settings.auth.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}
