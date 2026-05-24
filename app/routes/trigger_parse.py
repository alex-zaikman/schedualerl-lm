from fastapi import APIRouter, Depends, HTTPException

from app.config.dependencies import get_app_settings
from app.config.settings import Settings
from app.schemas.trigger_parse import TriggerParseRequest, TriggerParseResponse
from app.services.trigger_parse import TriggerParseError, parse_trigger_text

router = APIRouter(tags=["triggers"])


@router.post("/triggers/parse", response_model=TriggerParseResponse)
async def parse_trigger(
    body: TriggerParseRequest,
    settings: Settings = Depends(get_app_settings),
) -> TriggerParseResponse:
    try:
        return parse_trigger_text(
            body.text,
            settings.llm,
            timezone=body.timezone,
        )
    except TriggerParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
