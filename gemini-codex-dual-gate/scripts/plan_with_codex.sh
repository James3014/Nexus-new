#!/bin/bash
set -euo pipefail

source "$(dirname "$0")/lib/state.sh"
source "$(dirname "$0")/lib/artifact.sh"
source "$(dirname "$0")/lib/gate.sh"

MODEL="${CODEX_MODEL:-gpt-5.4}"

if ! ensure_real_codex_cli; then
  mkdir -p .ai
  [ -f .ai/state.json ] || cp "$(dirname "$0")/../templates/.ai/state.json" .ai/state.json
  seal_state
  set_status "BLOCKED"
  exit 1
fi

mkdir -p .ai
if [ ! -f .ai/state.json ]; then
  cp "$(dirname "$0")/../templates/.ai/state.json" .ai/state.json
  seal_state
fi
[ -f .ai/task.md ] || cp "$(dirname "$0")/../templates/.ai/task.md" .ai/task.md
[ -f .ai/constraints.md ] || cp "$(dirname "$0")/../templates/.ai/constraints.md" .ai/constraints.md
[ -f .ai/plan.md ] || cp "$(dirname "$0")/../templates/.ai/plan.md" .ai/plan.md
[ -f .ai/acceptance.md ] || cp "$(dirname "$0")/../templates/.ai/acceptance.md" .ai/acceptance.md

echo "🚀 Requesting Codex Plan Review (Model: $MODEL)..."

PROMPT="Review this plan strictly and reply exactly:
VERDICT: APPROVED|REVISE|BLOCKED
RATIONALE: <short>

TASK:
$(cat .ai/task.md 2>/dev/null || echo 'N/A')

CONSTRAINTS:
$(cat .ai/constraints.md 2>/dev/null || echo 'N/A')

PLAN:
$(cat .ai/plan.md)

ACCEPTANCE:
$(cat .ai/acceptance.md 2>/dev/null || echo 'N/A')"

# Review uncommitted diff context.
set +e
DIFF_OUTPUT="$(codex review --uncommitted -c "model=\"$MODEL\"" 2>&1)"
DIFF_EXIT=$?
set -e
DIFF_RECEIPT="$(write_command_receipt "plan-diff" "codex" "$MODEL" "codex review --uncommitted -c model=$MODEL" "$DIFF_EXIT" "$DIFF_OUTPUT")"

# Review explicit artifact prompt.
set +e
PROMPT_OUTPUT="$(codex review -c "model=\"$MODEL\"" "$PROMPT" 2>&1)"
PROMPT_EXIT=$?
set -e
PROMPT_RECEIPT="$(write_command_receipt "plan-prompt" "codex" "$MODEL" "codex review -c model=$MODEL <prompt>" "$PROMPT_EXIT" "$PROMPT_OUTPUT")"

{
  echo "### Review Context Prompt"
  echo "$PROMPT"
  echo
  echo "### Codex Diff Review Output"
  echo "$DIFF_OUTPUT"
  echo
  echo "### Codex Prompt Review Output"
  echo "$PROMPT_OUTPUT"
  echo
  echo "### Receipts"
  echo "$DIFF_RECEIPT"
  echo "$PROMPT_RECEIPT"
} > .ai/codex-plan-review.md

if [ "$DIFF_EXIT" -ne 0 ] || [ "$PROMPT_EXIT" -ne 0 ]; then
  if is_codex_quota_error "$DIFF_OUTPUT $PROMPT_OUTPUT"; then
    PLAN_HASH="$(calculate_hash ".ai/plan.md")"
    update_state "plan_hash" "\"$PLAN_HASH\""
    update_state "codex_quota_skipped" "true"
    update_state "merge_blocked" "true"
    append_history "codex_review_history" "{\"timestamp\": \"$(date)\", \"verdict\": \"SKIPPED_NO_QUOTA\", \"type\": \"plan\", \"model\": \"$MODEL\"}"
    set_status "PLAN_APPROVED_WITH_RISK"
    {
      echo
      echo "### Gate Note"
      echo "Codex quota unavailable. Plan gate accepted WITH RISK and merge remains blocked."
    } >> .ai/codex-plan-review.md
    echo "⚠️ Codex 額度不足（或達上限），Plan Review 以風險模式通過（PLAN_APPROVED_WITH_RISK）。"
    exit 0
  fi

  echo "❌ Codex CLI failed. Diff exit=$DIFF_EXIT prompt exit=$PROMPT_EXIT" >> .ai/codex-plan-review.md
  set_status "BLOCKED"
  echo "❌ Codex CLI Error. Check .ai/codex-plan-review.md"
  exit 1
fi

VERDICT="$(printf "%s\n%s\n" "$PROMPT_OUTPUT" "$DIFF_OUTPUT" | grep -oE "VERDICT: (APPROVED|REVISE|BLOCKED)" | head -n1 | awk '{print $2}')"
if [ -z "$VERDICT" ]; then
  set_status "PLAN_REVISE"
  {
    echo
    echo "### Gate Note"
    echo "Missing structured VERDICT from Codex output."
  } >> .ai/codex-plan-review.md
  echo "❌ Plan Review missing structured VERDICT. Please revise and rerun."
  exit 1
fi

echo -e "\n### Normalized Verdict\nVERDICT: $VERDICT" >> .ai/codex-plan-review.md
increment_count "codex_review_count"
append_history "codex_review_history" "{\"timestamp\": \"$(date)\", \"verdict\": \"$VERDICT\", \"type\": \"plan\", \"model\": \"$MODEL\"}"

if [ "$VERDICT" = "APPROVED" ]; then
  PLAN_HASH="$(calculate_hash ".ai/plan.md")"
  update_state "plan_hash" "\"$PLAN_HASH\""
  update_state "merge_blocked" "false"
  set_status "PLAN_APPROVED"
  echo "✅ Plan Approved by Codex ($MODEL)."
elif [ "$VERDICT" = "REVISE" ]; then
  set_status "PLAN_REVISE"
  echo "❌ Plan Rejected by Codex ($MODEL): REVISE. Please revise .ai/plan.md"
else
  set_status "PLAN_BLOCKED"
  echo "❌ Plan Blocked by Codex ($MODEL)."
  exit 1
fi
