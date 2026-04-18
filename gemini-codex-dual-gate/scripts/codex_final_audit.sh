#!/bin/bash
source "$(dirname "$0")/lib/state.sh"
source "$(dirname "$0")/lib/artifact.sh"
source "$(dirname "$0")/lib/lesson_writeback.sh"

MODEL="${CODEX_MODEL:-gpt-5.4}"

STATE=$(read_state | python3 -c "import json, sys; print(json.load(sys.stdin)['state'])")

if [ "$STATE" != "GEMINI_APPROVED" ] && [ "$STATE" != "AUDIT_REJECTED" ]; then
  echo "❌ Error: Gemini self-review must pass first. Current state: $STATE"
  exit 1
fi

# 1. Structural Checks
if ! grep -qE "AC-[0-9]+" .ai/acceptance.md; then
  echo "❌ BLOCKED: .ai/acceptance.md must have AC-1..AC-N numbering."
  set_status "BLOCKED"
  exit 1
fi

echo "🚀 Requesting Codex Scored Final Audit (Model: $MODEL)..."

PROMPT="Please perform a Scored High-Bar Final Audit.
Plan: $(cat .ai/plan.md 2>/dev/null)
Criteria: $(cat .ai/acceptance.md 2>/dev/null)
Changes: $(cat .ai/changed-files.md 2>/dev/null)
Tests: $(cat .ai/test-results.md 2>/dev/null)

Provide Scorecard:
coverage: 0-100
correctness: 0-100
risk: 0-100
test_quality: 0-100
maintainability: 0-100
overall: 0-100

AUDIT: PASS | REVISE | BLOCKED
PLAN_CONFORMANCE: PASS | FAIL
ACCEPTANCE_COVERAGE:
  - AC-1: PASS/FAIL (evidence: ...)
FINDINGS:
  - [SEVERITY] file:line - issue
REQUIRED_LESSONS:
  - <extracted lesson>

GATE RULES:
- overall < 85 => REVISE
- any CRITICAL => BLOCKED
- any AC FAIL => REVISE"

OUTPUT=$(echo "$PROMPT" | codex review --uncommitted -c "model=\"$MODEL\"" - 2>&1)
EXIT_CODE=$?

echo "$OUTPUT" > .ai/codex-scorecard.md

# 2. Parse Metrics
OVERALL=$(echo "$OUTPUT" | grep -oE "overall: [0-9]+" | awk '{print $2}')
[ -z "$OVERALL" ] && OVERALL=0
VERDICT=$(echo "$OUTPUT" | grep -oE "AUDIT: (PASS|REVISE|BLOCKED)" | head -n1 | cut -d' ' -f2)
AC_TOTAL=$(grep -cE "AC-[0-9]+" .ai/acceptance.md)
AC_PASS=$(echo "$OUTPUT" | grep -E "AC-[0-9]+: PASS" | wc -l)

# 3. Gate Logic
FINAL_VERDICT="$VERDICT"
if [ "$OVERALL" -lt 85 ]; then FINAL_VERDICT="REVISE"; fi
if [ "$AC_PASS" -lt "$AC_TOTAL" ]; then FINAL_VERDICT="REVISE"; fi
if echo "$OUTPUT" | grep -q "\[CRITICAL\]"; then FINAL_VERDICT="BLOCKED"; fi

# 4. Mandatory Lesson Writeback to Nexus
LESSONS=$(echo "$OUTPUT" | sed -n '/REQUIRED_LESSONS:/,$p' | sed '1d')
if [ ! -z "$LESSONS" ] && [ "$LESSONS" != "None" ]; then
  TASK_ID=$(cat .ai/task.md | head -n1 | sed 's/# Task Description//' | xargs)
  [ -z "$TASK_ID" ] && TASK_ID="codex-dual-gate-$(date +%s)"

  echo "### Codex Lesson ($(date))" >> .ai/lessons.md
  echo "$LESSONS" >> .ai/lessons.md

  L_ID=$(persist_lesson_to_nexus "$TASK_ID" "$LESSONS" "audit" "codex-final-audit" "fix-audit-findings")
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
else
  if [ "$FINAL_VERDICT" != "PASS" ]; then
    echo "❌ BLOCKED: REVISE/BLOCKED verdict requires lessons."
    set_status "BLOCKED"
    exit 1
  fi
fi

# Update state.json
update_state "codex_overall_score" "$OVERALL"
update_state "acceptance_pass_rate" "$(python3 -c "print($AC_PASS/$AC_TOTAL if $AC_TOTAL > 0 else 0.0)")"

increment_count "codex_review_count"
append_history "codex_review_history" "{\"timestamp\": \"$(date)\", \"verdict\": \"$FINAL_VERDICT\", \"score\": $OVERALL, \"type\": \"audit\"}"

if [ "$FINAL_VERDICT" == "PASS" ]; then
  set_status "DONE"
  echo "🎉 High-Bar Final Audit PASSED ($MODEL). Score: $OVERALL"
else
  set_status "AUDIT_REJECTED"
  echo "❌ High-Bar Final Audit $FINAL_VERDICT ($MODEL). Score: $OVERALL"
fi
