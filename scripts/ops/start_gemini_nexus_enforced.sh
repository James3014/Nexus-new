#!/bin/zsh
set -euo pipefail

NEXUS_ROOT="."
MODEL="${1:-gemini-3-flash-preview}"
APPROVAL_MODE="${2:-yolo}"
PROMPT_FILE="${3:-/tmp/gemini_nexus_task.md}"
REPORT_FILE="${REPORT_FILE:-$NEXUS_ROOT/.nexus/reports/gemini_invoke_report.json}"
INVOKER="$NEXUS_ROOT/scripts/ops/gemini_nexus_invoke.py"

if [[ ! -f "$INVOKER" ]]; then
  echo "[nexus-enforced] missing invoker: $INVOKER" >&2
  exit 2
fi

if [[ ! -f "$PROMPT_FILE" ]]; then
  cat >&2 <<EOF
[nexus-enforced] prompt file missing: $PROMPT_FILE
Create one first, e.g.:
  cat > /tmp/gemini_nexus_task.md <<'TASK'
  在 . 內實作你的任務（僅修改必要檔案），
  並執行驗收命令後回報：變更檔案、測試摘要、gate 結果。
  TASK
EOF
  exit 2
fi

echo "[nexus-enforced] root=$NEXUS_ROOT"
echo "[nexus-enforced] model=$MODEL approval_mode=$APPROVAL_MODE"
echo "[nexus-enforced] prompt_file=$PROMPT_FILE"
echo "[nexus-enforced] report_file=$REPORT_FILE"

cd "$NEXUS_ROOT"

echo "[nexus-enforced] preflight: ci_gate dry-run"
uv run scripts/ops/ci_gate.py --dry-run --wiki-drift-enforce-level p0 >/dev/null

echo "[nexus-enforced] invoke gemini via stable wrapper"
python3 "$INVOKER" \
  --preflight \
  --model "$MODEL" \
  --prompt-file "$PROMPT_FILE" \
  --report-file "$REPORT_FILE"

