#!/bin/bash
set -euo pipefail

# Gemini-Nexus Enforced Launch
# Usage:
#   bash scripts/ops/start_gemini_nexus_enforced.sh <prompt-file> [report-file] [timeout-sec]
#   bash scripts/ops/start_gemini_nexus_enforced.sh            # interactive gemini fallback

NEXUS_MACHINE_STATE_DIR="${NEXUS_MACHINE_STATE_DIR:-${NEXUS_STATE_DIR:-${TMPDIR:-/tmp}/nexus-machine-state}}"
NEXUS_STARTUP_REPORT_DIR="${NEXUS_STARTUP_REPORT_DIR:-$NEXUS_MACHINE_STATE_DIR/startup_hardening}"
export NEXUS_MACHINE_STATE_DIR NEXUS_STARTUP_REPORT_DIR
mkdir -p "$NEXUS_MACHINE_STATE_DIR" "$NEXUS_STARTUP_REPORT_DIR"

BRIEFING_PATH="$(bash scripts/ops/_nexus_enforced_briefing.sh "$NEXUS_MACHINE_STATE_DIR/enforced_agent_briefing.md")"
echo "📘 Enforced briefing generated: $BRIEFING_PATH"

bash scripts/ops/_nexus_preflight.sh || exit 1

# 🛡️ Nexus Startup Contract Check
export NEXUS_RUNNER="Gemini"
python3 scripts/ops/nexus_startup_contract_check.py || {
  echo "❌ [ENFORCEMENT-BLOCK] Startup Contract FAILED. Agent cannot proceed."
  exit 1
}
# `NEXUS_RUNNER` is only a startup-contract input. Keeping it in the
# environment changes Gemini CLI auth/headless behavior and can trigger an
# interactive browser prompt inside delegated rounds.
unset NEXUS_RUNNER

if [[ $# -ge 1 ]]; then
  PROMPT_FILE="$1"
  REPORT_FILE="${2:-$NEXUS_MACHINE_STATE_DIR/gemini_round_report.json}"
  TIMEOUT_SEC="${3:-240}"
  echo "🚀 Launching Gemini delegated round with Nexus enforcement..."
  exec bash scripts/ops/run_gemini_nexus_round.sh "$PROMPT_FILE" "$REPORT_FILE" "$TIMEOUT_SEC"
fi

echo "🚀 [ENFORCED-INTERACTIVE] Launching interactive Gemini shell..."
echo "🛡️ Startup Contract ACK: $(cat "$NEXUS_STARTUP_REPORT_DIR/startup_contract_ack.json" | grep ack_token)"
echo "📘 Loading Briefing: $BRIEFING_PATH"
# 強制輸出 Briefing 摘要
head -n 20 "$BRIEFING_PATH"

exec /Users/jameschen/.npm-global/bin/gemini
