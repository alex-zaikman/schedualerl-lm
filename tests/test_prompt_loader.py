from pathlib import Path

import pytest

from app.prompts.loader import PromptLoadError, load_prompt


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
