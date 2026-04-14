#!/bin/bash
set -euo pipefail

# Gemini-Nexus Enforced Launch
# Usage:
#   bash scripts/ops/start_gemini_nexus_enforced.sh <prompt-file> [report-file] [timeout-sec]
#   bash scripts/ops/start_gemini_nexus_enforced.sh            # interactive gemini fallback

bash scripts/ops/_nexus_preflight.sh || exit 1

if [[ $# -ge 1 ]]; then
  PROMPT_FILE="$1"
  REPORT_FILE="${2:-.nexus/reports/gemini_round_report.json}"
  TIMEOUT_SEC="${3:-240}"
  echo "🚀 Launching Gemini delegated round with Nexus enforcement..."
  exec bash scripts/ops/run_gemini_nexus_round.sh "$PROMPT_FILE" "$REPORT_FILE" "$TIMEOUT_SEC"
fi

echo "🚀 Launching interactive Gemini shell (preflight already passed)..."
exec /Users/jameschen/.npm-global/bin/gemini
