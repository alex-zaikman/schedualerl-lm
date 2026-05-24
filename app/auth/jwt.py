from datetime import datetime, timedelta, timezone

import jwt

from app.config.settings import AuthSettings


def decode_token(token: str, settings: AuthSettings) -> dict:
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )


def encode_token(
    settings: AuthSettings,
    *,
    sub: str,
    expires_in: timedelta,
    extra_claims: dict | None = None,
) -> str:
    payload: dict = {
        "sub": sub,
        "exp": datetime.now(timezone.utc) + expires_in,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
