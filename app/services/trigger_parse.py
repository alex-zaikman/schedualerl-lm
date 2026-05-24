import json
import logging
from datetime import datetime

from litellm import completion
from pydantic import TypeAdapter, ValidationError

from app.config.settings import LLMSettings
from app.prompts.loader import PromptLoadError, load_prompt
from app.scheduler.triggers import compute_next_run_at, trigger_config_from_spec
from app.schemas.tasks import CronTriggerSpec, TriggerSpec
from app.validation.cron import is_valid_cron_expression

logger = logging.getLogger(__name__)

_TRIGGER_SPEC_ADAPTER = TypeAdapter(TriggerSpec)


class TriggerParseError(Exception):
    pass


def _extract_content(response) -> str:
    content = response.choices[0].message.content
    if not content:
        raise TriggerParseError("LLM returned empty response")
    return content.strip()


def _parse_trigger_json(raw: str) -> TriggerSpec:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TriggerParseError(f"Invalid JSON: {exc}") from exc

    try:
        spec = _TRIGGER_SPEC_ADAPTER.validate_python(data)
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
    kwargs: dict = {
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


def parse_trigger_text(
    text: str,
    settings: LLMSettings,
    *,
    timezone: str = "UTC",
) -> tuple[str, dict, datetime | None]:
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

    last_error: str | None = None
    attempts = settings.max_retries + 1

    for attempt in range(attempts):
        try:
            raw = _call_llm(settings, messages)
            spec = _parse_trigger_json(raw)
            trigger_type = spec.type
            trigger_config = trigger_config_from_spec(spec)
            next_run_at = compute_next_run_at(spec)
            return trigger_type, trigger_config, next_run_at
        except TriggerParseError as exc:
            last_error = str(exc)
            logger.warning(
                "Trigger parse attempt %d/%d failed: %s",
                attempt + 1,
                attempts,
                last_error,
            )
            if attempt < attempts - 1:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous response was invalid: {last_error}. "
                            "Return corrected JSON only."
                        ),
                    }
                )

    raise TriggerParseError(last_error or "Failed to parse trigger")
