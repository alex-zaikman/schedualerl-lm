import os
import warnings

import httpx
import pytest


@pytest.fixture(scope="session")
def ollama_available():
    base = os.environ.get("LLM_API_BASE", "http://localhost:11434")
    try:
        resp = httpx.get(f"{base.rstrip('/')}/api/tags", timeout=2.0)
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama returned {resp.status_code}")
    except Exception as exc:
        warnings.warn(
            f"Ollama not available ({exc}); skipping LLM integration tests",
            UserWarning,
            stacklevel=2,
        )
        pytest.skip(f"Ollama not available: {exc}")
    return base
