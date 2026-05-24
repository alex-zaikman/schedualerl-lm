from fastapi import APIRouter, Depends

from app.auth.context import CurrentUser
from app.auth.dependencies import get_current_user
from app.schemas.api import MeResponse

router = APIRouter(tags=["api"])


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user_id=user.user_id)
