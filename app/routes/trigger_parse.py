from fastapi import APIRouter, Depends, HTTPException

from app.auth.context import CurrentUser
from app.auth.dependencies import get_current_user
from app.config.dependencies import get_app_settings
from app.config.settings import Settings
from app.schemas.trigger_parse import TriggerParseRequest, TriggerParseResponse
from app.services.trigger_parse import TriggerParseError, parse_trigger_text

router = APIRouter(tags=["triggers"])


@router.post("/triggers/parse")
async def parse_trigger(
    body: TriggerParseRequest,
    _user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_app_settings),
) -> TriggerParseResponse:
    try:
        trigger_type, trigger_config, next_run_at = parse_trigger_text(
            body.text,
            settings.llm,
            timezone=body.timezone,
        )
    except TriggerParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return TriggerParseResponse(
        trigger_type=trigger_type,
        trigger_config=trigger_config,
        next_run_at=next_run_at,
    )
