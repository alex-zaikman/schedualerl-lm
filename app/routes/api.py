from fastapi import APIRouter, Depends

from app.auth.context import CurrentUser
from app.auth.dependencies import get_current_user

router = APIRouter(tags=["api"])


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user)) -> dict[str, str]:
    return {"user_id": user.user_id}
