import jwt

from app.config.settings import AuthSettings


def decode_token(token: str, settings: AuthSettings) -> dict:
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )
