#!/bin/zsh
set -euo pipefail

NEXUS_ROOT="."
MODEL="${1:-gpt-5.4-mini}"
APPROVAL_MODE="${2:-full-auto}"
PROMPT_FILE="${3:-/tmp/antigravity_nexus_task.md}"
REPORT_FILE="${REPORT_FILE:-$NEXUS_ROOT/.nexus/reports/antigravity_invoke_report.txt}"
LOCK_FILE="${LOCK_FILE:-/tmp/nexus_antigravity_invoke.lock}"

if [[ ! -f "$PROMPT_FILE" ]]; then
  cat >&2 <<EOF
[nexus-enforced] prompt file missing: $PROMPT_FILE
Create one first, e.g.:
  cat > /tmp/antigravity_nexus_task.md <<'TASK'
  在 . 內完成指定任務，
  並回報變更檔案、測試摘要與 gate 結果。
  TASK
EOF
  exit 2
fi

if ! command -v codex >/dev/null 2>&1; then
  echo "[nexus-enforced] missing command: codex" >&2
  exit 2
fi

if [[ -e "$LOCK_FILE" ]]; then
  echo "[nexus-enforced] another antigravity run is active: $LOCK_FILE" >&2
  exit 3
fi

trap 'rm -f "$LOCK_FILE"' EXIT
echo "$$" > "$LOCK_FILE"

echo "[nexus-enforced] root=$NEXUS_ROOT"
echo "[nexus-enforced] model=$MODEL approval_mode=$APPROVAL_MODE"
echo "[nexus-enforced] prompt_file=$PROMPT_FILE"
echo "[nexus-enforced] report_file=$REPORT_FILE"

cd "$NEXUS_ROOT"

BRIEFING_PATH="$(bash scripts/ops/_nexus_enforced_briefing.sh .nexus/reports/enforced_agent_briefing.md)"
echo "[nexus-enforced] briefing=$BRIEFING_PATH"

# 🛡️ Nexus Startup Contract Check
export NEXUS_RUNNER="Codex"
python3 scripts/ops/nexus_startup_contract_check.py || {
  echo "❌ [ENFORCEMENT-BLOCK] Startup Contract FAILED. Codex cannot proceed."
  exit 1
}

echo "[nexus-enforced] invoke codex-nexus (enforced)"
if [[ "$APPROVAL_MODE" == "danger" ]]; then
  cat "$PROMPT_FILE" | codex exec -C "$NEXUS_ROOT" -m "$MODEL" --dangerously-bypass-approvals-and-sandbox - | tee "$REPORT_FILE"
else
  cat "$PROMPT_FILE" | codex exec -C "$NEXUS_ROOT" -m "$MODEL" --full-auto - | tee "$REPORT_FILE"
fi
