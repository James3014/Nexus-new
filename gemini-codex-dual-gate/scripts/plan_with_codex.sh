#!/bin/bash
source "$(dirname "$0")/lib/state.sh"
source "$(dirname "$0")/lib/artifact.sh"
source "$(dirname "$0")/lib/gate.sh"

MODEL="${CODEX_MODEL:-gpt-5.4}"

if ! ensure_real_codex_cli; then
  mkdir -p .ai
  [ -f .ai/state.json ] || cp "$(dirname "$0")/../templates/.ai/state.json" .ai/state.json
  set_status "BLOCKED"
  exit 1
fi

mkdir -p .ai
if [ ! -f .ai/state.json ]; then
  cp "$(dirname "$0")/../templates/.ai/state.json" .ai/state.json
fi

if [ ! -f .ai/task.md ]; then
  cp "$(dirname "$0")/../templates/.ai/task.md" .ai/task.md
fi

if [ ! -f .ai/constraints.md ]; then
  cp "$(dirname "$0")/../templates/.ai/constraints.md" .ai/constraints.md
fi

if [ ! -f .ai/plan.md ]; then
  cp "$(dirname "$0")/../templates/.ai/plan.md" .ai/plan.md
fi

if [ ! -f .ai/acceptance.md ]; then
  cp "$(dirname "$0")/../templates/.ai/acceptance.md" .ai/acceptance.md
fi

echo "🚀 Requesting Codex Plan Review (Model: $MODEL)..."

# Build prompt for plan review (kept as context artifact).
PROMPT="Please review the following plan artifacts and provide a verdict.
Task: $(cat .ai/task.md 2>/dev/null || echo 'N/A')
Constraints: $(cat .ai/constraints.md 2>/dev/null || echo 'N/A')
Plan: $(cat .ai/plan.md)
Acceptance Criteria: $(cat .ai/acceptance.md 2>/dev/null || echo 'N/A')

Output format:
VERDICT: APPROVED | REVISE | BLOCKED
Reasoning: <brief explanation>"

# Call Codex CLI in --uncommitted mode. Current CLI version rejects custom prompt in this mode.
OUTPUT=$(codex review --uncommitted -c "model=\"$MODEL\"" 2>&1)
EXIT_CODE=$?

{
  echo "### Review Context Prompt"
  echo "$PROMPT"
  echo
  echo "### Codex Raw Output"
  echo "$OUTPUT"
} > .ai/codex-plan-review.md

if [ $EXIT_CODE -ne 0 ]; then
  if is_codex_quota_error "$OUTPUT"; then
    update_state "codex_quota_skipped" "true"
    append_history "codex_review_history" "{\"timestamp\": \"$(date)\", \"verdict\": \"SKIPPED_NO_QUOTA\", \"type\": \"plan\", \"model\": \"$MODEL\"}"
    set_status "PLAN_APPROVED"
    {
      echo
      echo "### Gate Note"
      echo "Codex quota unavailable. Plan gate was skipped by policy."
    } >> .ai/codex-plan-review.md
    echo "⚠️ Codex 額度不足（或達上限），已跳過 Plan Review Gate。"
    exit 0
  fi

  echo "❌ Codex CLI failed with exit code $EXIT_CODE" >> .ai/codex-plan-review.md
  set_status "BLOCKED"
  echo "❌ Codex CLI Error. Check .ai/codex-plan-review.md"
  exit $EXIT_CODE
fi

# Parse Verdict
VERDICT=$(echo "$OUTPUT" | grep -oE "VERDICT: (APPROVED|REVISE|BLOCKED)" | head -n1 | cut -d' ' -f2)
if [ -z "$VERDICT" ]; then
  if echo "$OUTPUT" | grep -qiE "no issues found|no actionable findings"; then
    VERDICT="APPROVED"
  else
    VERDICT="REVISE"
  fi
fi

echo -e "\n### Normalized Verdict\nVERDICT: $VERDICT" >> .ai/codex-plan-review.md

# Update State
increment_count "codex_review_count"
append_history "codex_review_history" "{\"timestamp\": \"$(date)\", \"verdict\": \"$VERDICT\", \"type\": \"plan\", \"model\": \"$MODEL\"}"

if [ "$VERDICT" == "APPROVED" ]; then
  PLAN_HASH=$(calculate_hash ".ai/plan.md")
  update_state "plan_hash" "\"$PLAN_HASH\""
  set_status "PLAN_APPROVED"
  echo "✅ Plan Approved by Codex ($MODEL)."
else
  set_status "PLAN_REVISE"
  echo "❌ Plan Rejected by Codex ($MODEL): $VERDICT. Please revise .ai/plan.md"
fi
