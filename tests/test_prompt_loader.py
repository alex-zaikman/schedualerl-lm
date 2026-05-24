from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.prompts.loader import (
    CURRENT_DATE_PLACEHOLDER,
    CURRENT_ISO_DATETIME_PLACEHOLDER,
    DEFAULT_TIMEZONE_PLACEHOLDER,
    NEXT_FRIDAY_5PM_ISO_PLACEHOLDER,
    ONE_HOUR_LATER_ISO_PLACEHOLDER,
    TOMORROW_MORNING_ISO_PLACEHOLDER,
    PromptLoadError,
    build_trigger_parse_placeholders,
    load_prompt,
    render_trigger_parse_prompt,
)


def test_load_prompt_reads_file(tmp_path: Path):
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("  test prompt content  \n", encoding="utf-8")

    assert load_prompt(prompt_path) == "test prompt content"


def test_load_prompt_missing_file_raises(tmp_path: Path):
    with pytest.raises(PromptLoadError, match="Failed to read prompt file"):
        load_prompt(tmp_path / "missing.txt")


def test_load_prompt_empty_file_raises(tmp_path: Path):
    prompt_path = tmp_path / "empty.txt"
    prompt_path.write_text("   \n", encoding="utf-8")

    with pytest.raises(PromptLoadError, match="is empty"):
        load_prompt(prompt_path)


def test_build_trigger_parse_placeholders():
    now = datetime(2026, 5, 24, 8, 0, tzinfo=timezone.utc)
    placeholders = build_trigger_parse_placeholders(now=now, timezone="UTC")

    assert placeholders[CURRENT_ISO_DATETIME_PLACEHOLDER] == "2026-05-24T08:00:00+00:00"
    assert placeholders[DEFAULT_TIMEZONE_PLACEHOLDER] == "UTC"
    assert placeholders[CURRENT_DATE_PLACEHOLDER] == "2026-05-24"
    assert placeholders[TOMORROW_MORNING_ISO_PLACEHOLDER] == "2026-05-25T09:00:00+00:00"
    assert placeholders[ONE_HOUR_LATER_ISO_PLACEHOLDER] == "2026-05-24T09:00:00+00:00"
    assert placeholders[NEXT_FRIDAY_5PM_ISO_PLACEHOLDER] == "2026-05-29T17:00:00+00:00"


def test_render_trigger_parse_prompt_replaces_placeholders():
    now = datetime(2026, 5, 24, 8, 0, tzinfo=timezone.utc)
    content = (
        f"CURRENT TIME: {CURRENT_ISO_DATETIME_PLACEHOLDER}\n"
        f"DATE: {CURRENT_DATE_PLACEHOLDER}\n"
        f"DEFAULT TIMEZONE: {DEFAULT_TIMEZONE_PLACEHOLDER}"
    )

    rendered = render_trigger_parse_prompt(
        content,
        now=now,
        timezone="America/New_York",
    )

    assert "2026-05-24" in rendered
    assert "America/New_York" in rendered
    assert "[INJECT_" not in rendered


def test_render_trigger_parse_prompt_raises_on_unreplaced_placeholders():
    now = datetime(2026, 5, 24, 8, 0, tzinfo=timezone.utc)
    content = (
        "CURRENT TIME: [INJECT_CURRENT_ISO_DATETIME]\n"
        "OTHER: [INJECT_MISSING_HERE]"
    )

    with pytest.raises(PromptLoadError, match="Unreplaced placeholders"):
        render_trigger_parse_prompt(content, now=now, timezone="UTC")
