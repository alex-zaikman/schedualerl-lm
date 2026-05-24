from fastapi import Depends, HTTPException, Request, status

from app.auth.context import CurrentUser
from app.auth.security import require_bearer_token


def get_current_user(request: Request) -> CurrentUser:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return CurrentUser(user_id=user_id)


protected_dependencies = [
    Depends(require_bearer_token),
    Depends(get_current_user),
]
