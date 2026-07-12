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
TIMEOUT_SEC="${3:-420}"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "Prompt file not found: $PROMPT_FILE"
  exit 3
fi

REPO_ROOT="/Users/jameschen/Workspace/nexus"
cd "$REPO_ROOT"

GEMINI_BIN="/Users/jameschen/.npm-global/bin/gemini"
if [[ ! -x "$GEMINI_BIN" ]]; then
  echo "Gemini binary not found or not executable: $GEMINI_BIN"
  exit 4
fi
UV_BIN="${NEXUS_UV_BIN:-/Users/jameschen/.local/bin/uv}"
if [[ ! -x "$UV_BIN" ]]; then
  echo "uv binary not found or not executable: $UV_BIN"
  exit 5
fi
echo "[Gemini+Nexus] preflight..."
"$UV_BIN" run scripts/ops/gemini_nexus_invoke.py \
  --preflight \
  --preflight-only \
  --prompt "unused" \
  --report-file ".nexus/reports/gemini_preflight_round.json" \
  --timeout-sec 80 \
  --max-retries 0

# Always force the current Nexus armor contract into delegated Gemini tasks.
BRIEFING_PATH="${NEXUS_ENFORCED_BRIEFING_PATH:-.nexus/reports/enforced_agent_briefing.md}"
if [[ ! -f "$BRIEFING_PATH" ]]; then
  BRIEFING_PATH="$(bash scripts/ops/_nexus_enforced_briefing.sh "$BRIEFING_PATH")"
fi
NEXUS_PREAMBLE="$(cat "$BRIEFING_PATH")"

DELEGATED_CONTRACT=$(cat <<'EOF'
Delegated round contract:
1. Start as NEXUS_BOOTSTRAP_INCOMPLETE until command evidence proves bootstrap and wearing.
2. Do not use git stash, git clean, git restore, kill, pkill, live provider calls, remote clone, or unrelated file cleanup.
3. Change only the allowed files named by the task prompt.
4. Provide modified files, commands executed, key outputs, and residual risks.
5. If gates fail, report NOT DONE and provide next-round plan.
EOF
)
NEXUS_PREAMBLE="${NEXUS_PREAMBLE}

${DELEGATED_CONTRACT}"

MERGED_PROMPT_FILE="$(mktemp /tmp/nexus_gemini_prompt.XXXXXX.md)"
trap 'rm -f "$MERGED_PROMPT_FILE"' EXIT
{
  printf "%s\n\n" "$NEXUS_PREAMBLE"
  cat "$PROMPT_FILE"
} > "$MERGED_PROMPT_FILE"

# Dynamic timeout tuning by prompt size to avoid false timeout on heavy tasks.
PROMPT_BYTES="$(wc -c < "$MERGED_PROMPT_FILE" | tr -d ' ')"
INACTIVITY_TIMEOUT_SEC=120
if [[ "$PROMPT_BYTES" -ge 4000 ]]; then
  TIMEOUT_SEC=$(( TIMEOUT_SEC > 720 ? TIMEOUT_SEC : 720 ))
  INACTIVITY_TIMEOUT_SEC=300
elif [[ "$PROMPT_BYTES" -ge 2000 ]]; then
  TIMEOUT_SEC=$(( TIMEOUT_SEC > 480 ? TIMEOUT_SEC : 480 ))
  INACTIVITY_TIMEOUT_SEC=180
fi

echo "[Gemini+Nexus] tuned timeout: timeout_sec=${TIMEOUT_SEC}, inactivity_sec=${INACTIVITY_TIMEOUT_SEC}, prompt_bytes=${PROMPT_BYTES}"

echo "[Gemini+Nexus] dispatch start..."
# Use the reliable invoker instead of embedded python
# After 1 timeout, we record it and the skill/supervisor should handle fallback
# Here we just ensure the report is correct and classification is explicit.

set +e
"$UV_BIN" run scripts/ops/gemini_nexus_invoke.py \
  --prompt-file "$MERGED_PROMPT_FILE" \
  --report-file "$REPORT_FILE" \
  --timeout-sec "$TIMEOUT_SEC" \
  --inactivity-timeout-sec "$INACTIVITY_TIMEOUT_SEC" \
  --max-retries 1
EXIT_CODE=$?
set -e

if [[ $EXIT_CODE -ne 0 ]]; then
  # Check if it was a timeout to suggest fallback
  REASON=$(python3 -c "import json, sys; print(json.load(open('$REPORT_FILE')).get('reason', 'unknown'))" 2>/dev/null || echo "unknown")
  if [[ "$REASON" == "TIMEOUT_INACTIVITY" || "$REASON" == "TIMEOUT_WALLCLOCK" ]]; then
    echo "[Gemini+Nexus] Detected $REASON. Recommended fallback: local supervisor mode."
    # We could potentially trigger a local run here, but standard protocol is to report and let Codex decide.
    # To satisfy "auto-fallback to local supervisor mode" requirement in the runner:
    # We will mark the report status as 'infra_blocked' with 'fallback_recommended'
    python3 - "$REPORT_FILE" <<'PY'
import json, sys
from pathlib import Path
report_file = Path(sys.argv[1])
if report_file.exists():
    data = json.loads(report_file.read_text())
    data["status"] = "infra_blocked"
    data["fallback_recommended"] = True
    report_file.write_text(json.dumps(data, indent=2))
PY
  fi
  echo "[Gemini+Nexus] dispatch failed. report=$REPORT_FILE"
  exit $EXIT_CODE
fi

echo "[Gemini+Nexus] dispatch done. report=$REPORT_FILE"
