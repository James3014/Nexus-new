#!/bin/bash
set -euo pipefail

source "$(dirname "$0")/lib/state.sh"
source "$(dirname "$0")/lib/artifact.sh"
source "$(dirname "$0")/lib/lesson_writeback.sh"
source "$(dirname "$0")/lib/gate.sh"

MODEL="${CODEX_MODEL:-gpt-5.4}"

if ! ensure_real_codex_cli; then
  set_status "BLOCKED"
  exit 1
fi

STATE=$(read_state | python3 -c "import json, sys; print(json.load(sys.stdin)['state'])")
if [ "$STATE" != "GEMINI_APPROVED" ] && [ "$STATE" != "AUDIT_REJECTED" ]; then
  echo "❌ Error: Gemini self-review must pass first. Current state: $STATE"
  exit 1
fi

if ! grep -qE "AC-[0-9]+" .ai/acceptance.md; then
  echo "❌ BLOCKED: .ai/acceptance.md must have AC-1..AC-N numbering."
  set_status "BLOCKED"
  exit 1
fi

if ! grep -q "exit_code: 0" .ai/test-results.md 2>/dev/null; then
  echo "❌ BLOCKED: .ai/test-results.md lacks executed test evidence."
  set_status "BLOCKED"
  exit 1
fi

echo "🚀 Requesting Codex Scored Final Audit (Model: $MODEL)..."

PROMPT="Act as strict final auditor and reply exactly:
AUDIT: PASS|REVISE|BLOCKED
overall: <0-100>
PLAN_CONFORMANCE: PASS|FAIL
ACCEPTANCE_COVERAGE:
- AC-1: PASS|FAIL
FINDINGS:
- [SEVERITY] file:line - issue
REQUIRED_LESSONS:
- <lesson or None>

PLAN:
$(cat .ai/plan.md 2>/dev/null)

ACCEPTANCE:
$(cat .ai/acceptance.md 2>/dev/null)

CHANGED_FILES:
$(cat .ai/changed-files.md 2>/dev/null)

IMPLEMENTATION_REPORT:
$(cat .ai/implementation-report.md 2>/dev/null)

TEST_RESULTS:
$(cat .ai/test-results.md 2>/dev/null)"

# Diff review
set +e
DIFF_OUTPUT="$(codex review --uncommitted -c "model=\"$MODEL\"" 2>&1)"
DIFF_EXIT=$?
set -e
DIFF_RECEIPT="$(write_command_receipt "final-audit-diff" "codex" "$MODEL" "codex review --uncommitted -c model=$MODEL" "$DIFF_EXIT" "$DIFF_OUTPUT")"

# Prompt review
set +e
PROMPT_OUTPUT="$(codex review -c "model=\"$MODEL\"" "$PROMPT" 2>&1)"
PROMPT_EXIT=$?
set -e
PROMPT_RECEIPT="$(write_command_receipt "final-audit-prompt" "codex" "$MODEL" "codex review -c model=$MODEL <prompt>" "$PROMPT_EXIT" "$PROMPT_OUTPUT")"

{
  echo "### Audit Context Prompt"
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
} > .ai/codex-scorecard.md

if [ "$DIFF_EXIT" -ne 0 ] || [ "$PROMPT_EXIT" -ne 0 ]; then
  if is_codex_quota_error "$DIFF_OUTPUT $PROMPT_OUTPUT"; then
    # Even with quota skips, red-team invocation remains mandatory.
    set +e
    RED_Q_OUTPUT="$(python3 nexus/scripts/ops/red_team_pass.py 2>&1)"
    RED_Q_EXIT=$?
    set -e
    RED_Q_RECEIPT="$(write_command_receipt "final-audit-redteam-quota" "gemini" "gemini-3.1-pro-preview" "python3 nexus/scripts/ops/red_team_pass.py" "$RED_Q_EXIT" "$RED_Q_OUTPUT")"
    {
      echo
      echo "### Red Team Output (Quota Path)"
      echo "$RED_Q_OUTPUT"
      echo
      echo "### Red Team Receipt (Quota Path)"
      echo "$RED_Q_RECEIPT"
    } >> .ai/codex-scorecard.md
    if [ "$RED_Q_EXIT" -ne 0 ] || [ ! -f .nexus/state/red_team_verdict.json ] || [ ! -f .nexus/state/red_team_invocation_receipt.json ]; then
      set_status "BLOCKED"
      echo "❌ BLOCKED: quota path requires successful red-team gate with receipts."
      exit 1
    fi

    update_state "codex_quota_skipped" "true"
    update_state "merge_blocked" "true"
    append_history "codex_review_history" "{\"timestamp\": \"$(date)\", \"verdict\": \"SKIPPED_NO_QUOTA\", \"type\": \"audit\", \"model\": \"$MODEL\"}"
    set_status "DONE_WITH_RISK"
    {
      echo
      echo "### Gate Note"
      echo "Codex quota unavailable. Final audit accepted WITH RISK and merge remains blocked."
    } >> .ai/codex-scorecard.md
    echo "⚠️ Codex 額度不足（或達上限），Final Audit 以風險模式通過（DONE_WITH_RISK）。"
    exit 0
  fi

  echo "❌ Codex CLI failed. Diff exit=$DIFF_EXIT prompt exit=$PROMPT_EXIT" >> .ai/codex-scorecard.md
  set_status "BLOCKED"
  echo "❌ Codex CLI Error. Check .ai/codex-scorecard.md"
  exit 1
fi

OVERALL=$(printf "%s\n%s\n" "$PROMPT_OUTPUT" "$DIFF_OUTPUT" | grep -oE "overall: [0-9]+" | head -n1 | awk '{print $2}')
[ -z "${OVERALL:-}" ] && OVERALL=70
VERDICT=$(printf "%s\n%s\n" "$PROMPT_OUTPUT" "$DIFF_OUTPUT" | grep -oE "AUDIT: (PASS|REVISE|BLOCKED)" | head -n1 | awk '{print $2}')
AC_TOTAL=$(grep -cE "AC-[0-9]+" .ai/acceptance.md)
AC_PASS=$(printf "%s\n%s\n" "$PROMPT_OUTPUT" "$DIFF_OUTPUT" | grep -E "AC-[0-9]+: PASS" | wc -l | tr -d ' ')

if [ -z "${VERDICT:-}" ]; then
  set_status "AUDIT_REJECTED"
  {
    echo
    echo "### Gate Note"
    echo "Missing structured AUDIT verdict from Codex output."
  } >> .ai/codex-scorecard.md
  echo "❌ Missing structured AUDIT verdict from Codex output."
  exit 1
fi

FINAL_VERDICT="$VERDICT"
if [ "$OVERALL" -lt 85 ]; then FINAL_VERDICT="REVISE"; fi
if [ "$AC_PASS" -lt "$AC_TOTAL" ]; then FINAL_VERDICT="REVISE"; fi
if printf "%s\n%s\n" "$PROMPT_OUTPUT" "$DIFF_OUTPUT" | grep -q "\[CRITICAL\]"; then FINAL_VERDICT="BLOCKED"; fi

# Mandatory red-team gate (real invocation evidence required).
set +e
RED_OUTPUT="$(python3 nexus/scripts/ops/red_team_pass.py 2>&1)"
RED_EXIT=$?
set -e
RED_RECEIPT="$(write_command_receipt "final-audit-redteam" "gemini" "gemini-3.1-pro-preview" "python3 nexus/scripts/ops/red_team_pass.py" "$RED_EXIT" "$RED_OUTPUT")"
{
  echo
  echo "### Red Team Output"
  echo "$RED_OUTPUT"
  echo
  echo "### Red Team Receipt"
  echo "$RED_RECEIPT"
} >> .ai/codex-scorecard.md

if [ "$RED_EXIT" -ne 0 ] || [ ! -f .nexus/state/red_team_verdict.json ] || [ ! -f .nexus/state/red_team_invocation_receipt.json ]; then
  set_status "BLOCKED"
  echo "❌ BLOCKED: Red-team gate failed or missing invocation receipts."
  exit 1
fi

LESSONS=$(printf "%s\n%s\n" "$PROMPT_OUTPUT" "$DIFF_OUTPUT" | sed -n '/REQUIRED_LESSONS:/,$p' | sed '1d')
LESSONS_NORMALIZED=$(echo "$LESSONS" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | sed '/^$/d')
if [ -n "$LESSONS_NORMALIZED" ] && ! echo "$LESSONS_NORMALIZED" | grep -qiE '^(none|n/a)$'; then
  TASK_ID=$(cat .ai/task.md | head -n1 | sed 's/# Task Description//' | xargs)
  [ -z "$TASK_ID" ] && TASK_ID="codex-dual-gate-$(date +%s)"

  echo "### Codex Lesson ($(date))" >> .ai/lessons.md
  echo "$LESSONS_NORMALIZED" >> .ai/lessons.md

  L_ID=$(persist_lesson_to_nexus "$TASK_ID" "$LESSONS_NORMALIZED" "audit" "codex-final-audit" "fix-audit-findings")
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

update_state "codex_overall_score" "$OVERALL"
update_state "acceptance_pass_rate" "$(python3 -c "print($AC_PASS/$AC_TOTAL if $AC_TOTAL > 0 else 0.0)")"

increment_count "codex_review_count"
append_history "codex_review_history" "{\"timestamp\": \"$(date)\", \"verdict\": \"$FINAL_VERDICT\", \"score\": $OVERALL, \"type\": \"audit\"}"

if [ "$FINAL_VERDICT" = "PASS" ]; then
  update_state "merge_blocked" "false"
  set_status "DONE"
  echo "🎉 High-Bar Final Audit PASSED ($MODEL). Score: $OVERALL"
elif [ "$FINAL_VERDICT" = "REVISE" ]; then
  set_status "AUDIT_REJECTED"
  echo "❌ High-Bar Final Audit REVISE ($MODEL). Score: $OVERALL"
else
  set_status "BLOCKED"
  echo "❌ High-Bar Final Audit BLOCKED ($MODEL). Score: $OVERALL"
  exit 1
fi
