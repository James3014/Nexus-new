#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/lib/state.sh"
source "$(dirname "$0")/lib/lesson_writeback.sh"

GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.1-pro-preview}"

echo "🚀 Requesting Gemini Scored Self-Review (Model: $GEMINI_MODEL)..."

PROMPT="Please perform a Scored Self-Review on this implementation.
Plan: $(cat .ai/plan.md 2>/dev/null)
Changes: $(cat .ai/changed-files.md 2>/dev/null)
Report: $(cat .ai/implementation-report.md 2>/dev/null)

You MUST provide the following Scorecard:
coverage: 0-100
correctness: 0-100
risk: 0-100
test_quality: 0-100
maintainability: 0-100
overall: 0-100

TOP_ISSUES: (up to 5, include [SEVERITY])
REQUIRED_LESSONS: (extract lessons if any failures or issues found)

If overall < 85 or any CRITICAL finding, VERDICT is REVISE."

OUTPUT=$(gemini -m "$GEMINI_MODEL" -p "/code-review" --output-format text "$PROMPT" 2>&1)
EXIT_CODE=$?

echo "$OUTPUT" > .ai/gemini-scorecard.md

# Parse Scores
OVERALL=$(echo "$OUTPUT" | grep -oE "overall: [0-9]+" | awk '{print $2}')
[ -z "$OVERALL" ] && OVERALL=0

update_state "gemini_overall_score" "$OVERALL"
increment_count "gemini_review_count"

# Check Gate
if [ "$OVERALL" -ge 85 ]; then
  VERDICT="APPROVED"
  set_status "GEMINI_APPROVED"
  echo "✅ Gemini Scorecard: $OVERALL. APPROVED."
else
  VERDICT="REVISE"
  set_status "REVISING_IMPLEMENTATION"
  echo "❌ Gemini Scorecard: $OVERALL. REVISE REQUIRED."
fi

# Mandatory Lesson Writeback to Nexus
LESSONS=$(echo "$OUTPUT" | sed -n '/REQUIRED_LESSONS:/,$p' | sed '1d')
if [ ! -z "$LESSONS" ] && [ "$LESSONS" != "None" ]; then
  TASK_ID=$(cat .ai/task.md | head -n1 | sed 's/# Task Description//' | xargs)
  [ -z "$TASK_ID" ] && TASK_ID="gemini-dual-gate-$(date +%s)"

  echo "### Gemini Lesson ($(date))" >> .ai/lessons.md
  echo "$LESSONS" >> .ai/lessons.md

  L_ID=$(persist_lesson_to_nexus "$TASK_ID" "$LESSONS" "implementation" "gemini-self-review" "fix-implementation")
  if [ $? -eq 0 ]; then
    update_state "lessons_written_to_nexus" "true"
    append_history "lesson_event_ids" "\"$L_ID\""
    increment_count "lessons_count"
    echo "✅ Lesson written to Nexus Official Ledger ($L_ID)"
  else
    echo "❌ ERROR: Nexus Official Writeback failed."
    set_status "BLOCKED"
    exit 1
  fi
fi

append_history "gemini_review_history" "{\"timestamp\": \"$(date)\", \"verdict\": \"$VERDICT\", \"score\": $OVERALL, \"model\": \"$GEMINI_MODEL\"}"
