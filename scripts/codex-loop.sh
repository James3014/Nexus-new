#!/bin/bash
# 🛡️ Codex-Loop 2.0 (Lvl 16 Cognitive Loop)
# Muse-Core 的強制跨模型程式碼防護鎖 - 基於 Python Brain 的認知閉環版本
# 支援 Inner Loop 錯誤報告匯出至 /tmp/codex_loop_report.md
# 🛡️ SSoT: Relocatable Public Version
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRAIN_SCRIPT="${SCRIPT_DIR}/codex_loop_brain.py"
HANDOFF_SCRIPT="${SCRIPT_DIR}/core/gemini_handoff.py"

EMIT_HANDOFF=0
HANDOFF_ONLY=0
HANDOFF_OUTPUT="/tmp/gemini_handoff_prompt.txt"
PASSTHROUGH_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --emit-gemini-handoff)
      EMIT_HANDOFF=1
      shift
      ;;
    --handoff-only)
      HANDOFF_ONLY=1
      EMIT_HANDOFF=1
      shift
      ;;
    --handoff-output)
      HANDOFF_OUTPUT="$2"
      shift 2
      ;;
    *)
      PASSTHROUGH_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ "${HANDOFF_ONLY}" -eq 0 ]]; then
  python3 "$BRAIN_SCRIPT" "${PASSTHROUGH_ARGS[@]}"
  STATUS=$?
else
  STATUS=0
fi

if [[ "${EMIT_HANDOFF}" -eq 1 ]]; then
  if [[ -f /tmp/codex_next_action.json ]]; then
    python3 "$HANDOFF_SCRIPT" --input /tmp/codex_next_action.json --output "$HANDOFF_OUTPUT"
    HANDOFF_STATUS=$?
    if [[ "$HANDOFF_STATUS" -eq 0 ]]; then
      echo "Gemini handoff prompt written: $HANDOFF_OUTPUT"
    else
      echo "Failed to generate Gemini handoff prompt (exit=$HANDOFF_STATUS)." >&2
    fi
  else
    echo "No /tmp/codex_next_action.json found. Run codex-loop first or remove --handoff-only." >&2
    HANDOFF_STATUS=2
  fi
fi

if [[ "${HANDOFF_ONLY}" -eq 1 && "${EMIT_HANDOFF}" -eq 1 ]]; then
  exit "${HANDOFF_STATUS:-0}"
fi

exit "$STATUS"
