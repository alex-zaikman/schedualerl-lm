#!/usr/bin/env bash
# Create a daily scheduled webhook task against a local schedulerlm instance.
#
# Prerequisites:
#   - schedulerlm running at http://localhost:8000 (see README.md)
#   - .env with AUTH_JWT_SECRET (for mint_dev_jwt.py)
#   - Ollama with ollama/llama3.2 for text triggers (docker compose includes ollama)
#   - WEBHOOK_URL from https://webhook.site (copy your unique URL from the page)
#
# Usage:
#   WEBHOOK_URL=https://webhook.site/your-unique-id ./examples/create_daily_task.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${BASE_URL:-http://localhost:8000}"
USER_ID="${USER_ID:-user-123}"

if [[ -z "${WEBHOOK_URL:-}" ]]; then
  echo "Set WEBHOOK_URL to your unique URL from https://webhook.site" >&2
  exit 1
fi

cd "$ROOT"

TOKEN="$(uv run python scripts/mint_dev_jwt.py --sub "$USER_ID")"

echo "Creating task (webhook: $WEBHOOK_URL) ..."
curl -sf -X POST "$BASE_URL/api/v1/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"webhook_url\": \"$WEBHOOK_URL\",
    \"parameters\": {\"source\": \"schedulerlm\", \"example\": \"create_daily_task\"},
    \"trigger\": {
      \"type\": \"text\",
      \"text\": \"every day at 9am\",
      \"timezone\": \"UTC\"
    }
  }" | python -m json.tool

echo
echo "Active tasks:"
curl -sf -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/v1/tasks?active_only=true" | python -m json.tool

echo
echo "When the task fires, inspect the request at https://webhook.site"
