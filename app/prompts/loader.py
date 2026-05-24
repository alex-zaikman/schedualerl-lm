from pathlib import Path

DEFAULT_TRIGGER_PARSE_PROMPT_PATH = Path(__file__).resolve().parent / "trigger_parse.txt"


class PromptLoadError(Exception):
    pass


def load_prompt(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise PromptLoadError(f"Failed to read prompt file {path}: {exc}") from exc

    if not content:
        raise PromptLoadError(f"Prompt file {path} is empty")

    return content
