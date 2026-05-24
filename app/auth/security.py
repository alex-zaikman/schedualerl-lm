from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    description="JWT from: uv run python scripts/mint_dev_jwt.py --sub <user-id>",
)


def require_bearer_token(
    _credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> None:
    """OpenAPI-only dependency; JWT validation is handled by AuthMiddleware."""
