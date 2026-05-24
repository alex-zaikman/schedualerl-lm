from fastapi import APIRouter, Depends, HTTPException, status

from app.config.dependencies import get_app_settings
from app.config.settings import Settings
from app.schemas.trigger_parse import TriggerParseRequest, TriggerParseResponse
from app.services.trigger_parse import TriggerParseError, parse_trigger_text

router = APIRouter(tags=["triggers"])


@router.post(
    "/triggers/parse",
    response_model=TriggerParseResponse,
    summary="Parse natural-language schedule text",
    description=(
        "Parses schedule text into a structured trigger without creating a task. "
        "Use this to preview or validate natural language before calling POST /tasks."
    ),
)
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
