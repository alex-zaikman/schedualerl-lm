import json
import logging
from typing import Any

from litellm import completion
from pydantic import TypeAdapter, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt

from app.config.settings import LLMSettings
from app.prompts.loader import PromptLoadError, load_prompt
from app.scheduler.triggers import compute_next_run_at, trigger_config_from_spec
from app.schemas.tasks import CronTriggerSpec, StructuredTriggerSpec, TextTriggerSpec, TriggerSpec
from app.schemas.trigger_parse import TriggerParseResponse
from app.validation.cron import is_valid_cron_expression

logger = logging.getLogger(__name__)

_STRUCTURED_TRIGGER_SPEC_ADAPTER = TypeAdapter(StructuredTriggerSpec)


class TriggerParseError(Exception):
    pass


def _extract_content(response) -> str:
    content = response.choices[0].message.content
    if not content:
        raise TriggerParseError("LLM returned empty response")
    return content.strip()


def _parse_trigger_json(raw: str) -> StructuredTriggerSpec:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TriggerParseError(f"Invalid JSON: {exc}") from exc

    try:
        spec = _STRUCTURED_TRIGGER_SPEC_ADAPTER.validate_python(data)
    except ValidationError as exc:
        raise TriggerParseError(f"Invalid trigger spec: {exc}") from exc

    if isinstance(spec, CronTriggerSpec) and not is_valid_cron_expression(spec.expression):
        raise TriggerParseError(f"Invalid cron expression: {spec.expression!r}")

    try:
        compute_next_run_at(spec)
    except Exception as exc:
        raise TriggerParseError(f"Trigger cannot be scheduled: {exc}") from exc

    return spec


def _call_llm(
    settings: LLMSettings,
    messages: list[dict[str, str]],
) -> str:
    kwargs: dict[str, Any] = {
        "model": settings.model,
        "messages": messages,
        "api_base": settings.api_base,
        "timeout": settings.timeout_seconds,
        "response_format": {"type": "json_object"},
    }
    if settings.api_key is not None:
        kwargs["api_key"] = settings.api_key.get_secret_value()

    try:
        response = completion(**kwargs)
    except Exception as exc:
        raise TriggerParseError(f"LLM request failed: {exc}") from exc

    return _extract_content(response)


def parse_trigger_text_to_spec(
    text: str,
    settings: LLMSettings,
    *,
    timezone: str = "UTC",
) -> StructuredTriggerSpec:
    try:
        system_prompt = load_prompt(settings.trigger_parse_prompt_path)
    except PromptLoadError as exc:
        raise TriggerParseError(str(exc)) from exc

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"Convert this scheduling request to a trigger spec JSON.\n"
                f"Default timezone hint: {timezone}\n"
                f"Request: {text}"
            ),
        },
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
        return _parse_trigger_json(raw)

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
    if isinstance(spec, TextTriggerSpec):
        return parse_trigger_text_to_spec(spec.text, settings, timezone=spec.timezone)
    return spec
