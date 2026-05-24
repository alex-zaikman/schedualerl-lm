import os
import warnings

import httpx
import pytest

from tests.constants import TEST_LLM_WARMUP_TIMEOUT_SECONDS


def _ollama_model_name() -> str:
    raw = os.environ.get("LLM_MODEL", "ollama/llama3.2")
    return raw.removeprefix("ollama/")


@pytest.fixture(scope="session")
def ollama_available():
    base = os.environ.get("LLM_API_BASE", "http://localhost:11434").rstrip("/")
    try:
        resp = httpx.get(f"{base}/api/tags", timeout=2.0)
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama returned {resp.status_code}")
    except Exception as exc:
        warnings.warn(
            f"Ollama not available ({exc}); skipping LLM integration tests",
            UserWarning,
            stacklevel=2,
        )
        pytest.skip(f"Ollama not available: {exc}")

    model = _ollama_model_name()
    try:
        resp = httpx.post(
            f"{base}/api/generate",
            json={
                "model": model,
                "prompt": "{}",
                "stream": False,
                "options": {"num_predict": 1},
            },
            timeout=TEST_LLM_WARMUP_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Ollama warmup returned {resp.status_code}: {resp.text[:200]}"
            )
    except Exception as exc:
        warnings.warn(
            f"Ollama warmup failed ({exc}); skipping LLM integration tests",
            UserWarning,
            stacklevel=2,
        )
        pytest.skip(f"Ollama warmup failed: {exc}")

    return base
