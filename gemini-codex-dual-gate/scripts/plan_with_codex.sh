#!/bin/bash
source "$(dirname "$0")/lib/state.sh"
source "$(dirname "$0")/lib/artifact.sh"
source "$(dirname "$0")/lib/gate.sh"

MODEL="${CODEX_MODEL:-gpt-5.4}"

mkdir -p .ai
if [ ! -f .ai/state.json ]; then
  cp "$(dirname "$0")/../templates/.ai/state.json" .ai/state.json
fi

if [ ! -f .ai/plan.md ]; then
  cp "$(dirname "$0")/../templates/.ai/plan.md" .ai/plan.md
fi

echo "🚀 Requesting Codex Plan Review (Model: $MODEL)..."

# Build prompt for plan review
PROMPT="Please review the following plan artifacts and provide a verdict.
Task: $(cat .ai/task.md 2>/dev/null || echo 'N/A')
Constraints: $(cat .ai/constraints.md 2>/dev/null || echo 'N/A')
Plan: $(cat .ai/plan.md)
Acceptance Criteria: $(cat .ai/acceptance.md 2>/dev/null || echo 'N/A')

Output format:
VERDICT: APPROVED | REVISE | BLOCKED
Reasoning: <brief explanation>"

# Call real Codex CLI via stdin to avoid arg issues
OUTPUT=$(echo "$PROMPT" | codex review --uncommitted -c "model=\"$MODEL\"" - 2>&1)
EXIT_CODE=$?

echo "$OUTPUT" > .ai/codex-plan-review.md

if [ $EXIT_CODE -ne 0 ]; then
  echo "❌ Codex CLI failed with exit code $EXIT_CODE" >> .ai/codex-plan-review.md
  set_status "BLOCKED"
  echo "❌ Codex CLI Error. Check .ai/codex-plan-review.md"
  exit $EXIT_CODE
fi

# Parse Verdict
VERDICT=$(echo "$OUTPUT" | grep -oE "VERDICT: (APPROVED|REVISE|BLOCKED)" | head -n1 | cut -d' ' -f2)

if [ -z "$VERDICT" ]; then
  echo "❌ Failed to parse VERDICT from Codex output." >> .ai/codex-plan-review.md
  set_status "BLOCKED"
  echo "❌ Parse Error. Check .ai/codex-plan-review.md"
  exit 1
fi

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
