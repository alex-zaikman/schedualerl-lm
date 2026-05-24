from fastapi import HTTPException, Request

from app.auth.context import CurrentUser


def get_current_user(request: Request) -> CurrentUser:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return CurrentUser(user_id=user_id)
