#!/bin/bash
set -euo pipefail

# Usage:
#   bash scripts/ops/run_gemini_nexus_round.sh /tmp/round_task.md .nexus/reports/gemini_round_report.json

if [[ $# -lt 2 ]]; then
  echo "Usage: bash scripts/ops/run_gemini_nexus_round.sh <prompt-file> <report-file> [timeout-sec]"
  exit 2
fi

PROMPT_FILE="$1"
REPORT_FILE="$2"
TIMEOUT_SEC="${3:-700}"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "Prompt file not found: $PROMPT_FILE"
  exit 3
fi

REPO_ROOT="/Users/jameschen/Workspace/nexus"
cd "$REPO_ROOT"

echo "[Gemini+Nexus] clearing stale lock..."
rm -f /private/tmp/nexus_gemini_invoke.lock || true

echo "[Gemini+Nexus] preflight..."
uv run python3 scripts/ops/gemini_nexus_invoke.py \
  --preflight \
  --preflight-only \
  --prompt "reply with exactly: OK" \
  --timeout-sec 30 \
  --max-retries 0 \
  --report-file .nexus/reports/gemini_preflight_round.json

echo "[Gemini+Nexus] dispatch start..."
uv run python3 scripts/ops/gemini_nexus_invoke.py \
  --prompt-file "$PROMPT_FILE" \
  --timeout-sec "$TIMEOUT_SEC" \
  --inactivity-timeout-sec 90 \
  --max-retries 0 \
  --report-file "$REPORT_FILE"

echo "[Gemini+Nexus] dispatch done. report=$REPORT_FILE"
