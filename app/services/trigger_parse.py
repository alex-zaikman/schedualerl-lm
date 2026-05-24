import json
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from litellm import completion
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt

from app.config.settings import LLMSettings
from app.parsing.relative_schedule import try_parse_once_schedule
from app.prompts.loader import PromptLoadError, load_prompt, render_trigger_parse_prompt
from app.scheduler.triggers import compute_next_run_at, trigger_config_from_spec
from app.schemas.tasks import CronTriggerSpec, StructuredTriggerSpec, TextTriggerSpec, TriggerSpec
from app.schemas.trigger_parse import TriggerParseLLMOutput, TriggerParseResponse, trigger_spec_from_llm_output
from app.validation.cron import is_valid_cron_expression

logger = logging.getLogger(__name__)


class TriggerParseError(Exception):
    pass


def _trigger_parse_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "trigger_parse",
            "schema": TriggerParseLLMOutput.model_json_schema(by_alias=True),
            "strict": True,
        },
    }


def _extract_content(response) -> str:
    content = response.choices[0].message.content
    if not content:
        raise TriggerParseError("LLM returned empty response")
    return content.strip()


def _log_failed_parse(raw: str, exc: Exception) -> None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    thought = data.get("_thought")
    if thought:
        logger.warning("Trigger parse failed (%s); model thought: %s", exc, thought)


def _parse_trigger_json(raw: str, *, timezone: str) -> StructuredTriggerSpec:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TriggerParseError(f"Invalid JSON: {exc}") from exc

    try:
        llm_output = TriggerParseLLMOutput.model_validate(data)
    except ValidationError as exc:
        _log_failed_parse(raw, exc)
        raise TriggerParseError(f"Invalid trigger parse output: {exc}") from exc

    try:
        spec = trigger_spec_from_llm_output(llm_output, timezone=timezone)
    except (ValueError, ValidationError) as exc:
        _log_failed_parse(raw, exc)
        raise TriggerParseError(f"Invalid trigger spec: {exc}") from exc

    match spec:
        case CronTriggerSpec(expression=expression) if not is_valid_cron_expression(expression):
            _log_failed_parse(raw, TriggerParseError(f"Invalid cron expression: {expression!r}"))
            raise TriggerParseError(f"Invalid cron expression: {expression!r}")

    try:
        compute_next_run_at(spec)
    except Exception as exc:
        _log_failed_parse(raw, exc)
        raise TriggerParseError(f"Trigger cannot be scheduled: {exc}") from exc

    return spec


def _call_llm(
    settings: LLMSettings,
    messages: list[dict[str, str]],
) -> str:
    base_kwargs: dict[str, Any] = {
        "model": settings.model,
        "messages": messages,
        "api_base": settings.api_base,
        "timeout": settings.timeout_seconds,
    }
    if settings.api_key is not None:
        base_kwargs["api_key"] = settings.api_key.get_secret_value()

    response_formats: list[dict[str, Any] | None] = [
        _trigger_parse_response_format(),
        {"type": "json_object"},
        None,
    ]
    last_exc: Exception | None = None

    for response_format in response_formats:
        kwargs = dict(base_kwargs)
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            response = completion(**kwargs)
        except Exception as exc:
            last_exc = exc
            continue
        return _extract_content(response)

    raise TriggerParseError(f"LLM request failed: {last_exc}") from last_exc


def parse_trigger_text_to_spec(
    text: str,
    settings: LLMSettings,
    *,
    timezone: str = "UTC",
) -> StructuredTriggerSpec:
    now = datetime.now(ZoneInfo(timezone))

    once_spec = try_parse_once_schedule(text, now=now, timezone=timezone)
    if once_spec is not None:
        try:
            compute_next_run_at(once_spec)
        except Exception as exc:
            raise TriggerParseError(f"Trigger cannot be scheduled: {exc}") from exc
        return once_spec

    try:
        prompt_template = load_prompt(settings.trigger_parse_prompt_path)
        system_prompt = render_trigger_parse_prompt(
            prompt_template,
            now=now,
            timezone=timezone,
        )
    except PromptLoadError as exc:
        raise TriggerParseError(str(exc)) from exc

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]

    attempts = settings.max_retries + 1

    def _after_retry(retry_state) -> None:
        if not retry_state.outcome.failed:
            return
        exc = retry_state.outcome.exception()
        logger.warning(
            "Trigger parse attempt %d/%d failed: %s",
            retry_state.attempt_number,
            attempts,
            exc,
        )

    def _before_sleep(retry_state) -> None:
        exc = retry_state.outcome.exception()
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Your previous response was invalid: {exc}. "
                    "Return corrected JSON only."
                ),
            }
        )

    @retry(
        stop=stop_after_attempt(attempts),
        retry=retry_if_exception_type(TriggerParseError),
        before_sleep=_before_sleep,
        after=_after_retry,
        reraise=True,
    )
    def _parse_once() -> StructuredTriggerSpec:
        raw = _call_llm(settings, messages)
        return _parse_trigger_json(raw, timezone=timezone)

    return _parse_once()


def parse_trigger_text(
    text: str,
    settings: LLMSettings,
    *,
    timezone: str = "UTC",
) -> TriggerParseResponse:
    spec = parse_trigger_text_to_spec(text, settings, timezone=timezone)
    return TriggerParseResponse(
        trigger_type=spec.type,
        trigger_config=trigger_config_from_spec(spec),
        next_run_at=compute_next_run_at(spec),
    )


def resolve_trigger_spec(
    spec: TriggerSpec,
    settings: LLMSettings,
) -> StructuredTriggerSpec:
    match spec:
        case TextTriggerSpec(text=text, timezone=timezone):
            return parse_trigger_text_to_spec(text, settings, timezone=timezone)
        case _:
            return spec
