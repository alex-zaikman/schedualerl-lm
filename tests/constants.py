from datetime import datetime, timezone

TEST_JWT_SECRET = "test-jwt-secret-with-enough-length-for-hs256"
TEST_USER_ID = "test-user-123"
OTHER_USER_ID = "other-user-456"
FROZEN_TIME = datetime(2026, 5, 24, 8, 0, tzinfo=timezone.utc)

# Local Ollama on CPU often exceeds the app default (30s) for trigger-parse prompts.
TEST_LLM_TIMEOUT_SECONDS = 180.0
TEST_LLM_MAX_RETRIES = 1
TEST_LLM_WARMUP_TIMEOUT_SECONDS = 180.0
