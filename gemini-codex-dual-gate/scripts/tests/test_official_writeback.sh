#!/bin/bash
echo "=== Testing Official Nexus Writeback & Gate ==="

reset_state() {
  rm -rf .ai
  mkdir -p .ai
  cp gemini-codex-dual-gate/templates/.ai/state.json .ai/state.json
  echo "# Task Description" > .ai/task.md
  echo "TEST-TASK-001" >> .ai/task.md
  echo "# Acceptance" > .ai/acceptance.md
  echo "- AC-1: Pass" >> .ai/acceptance.md
  echo "# Test Results" > .ai/test-results.md
  echo "## Summary\n## Details" >> .ai/test-results.md
}

echo "1. Testing REVISE with Successful Writeback..."
reset_state
# Set state to GEMINI_APPROVED to enter audit
python3 -c "import json; d=json.load(open('.ai/state.json')); d['state']='GEMINI_APPROVED'; json.dump(d, open('.ai/state.json', 'w'))"

# Mock codex output for REVISE
export MOCK_OUTPUT="AUDIT: REVISE
overall: 70
PLAN_CONFORMANCE: PASS
ACCEPTANCE_COVERAGE:
  - AC-1: FAIL
FINDINGS:
  - [HIGH] Missing edge case
REQUIRED_LESSONS:
  - Add boundary check for input array."

codex() { echo "$MOCK_OUTPUT"; }
export -f codex
bash gemini-codex-dual-gate/scripts/codex_final_audit.sh
cat .ai/state.json | grep -E "state|lessons_written_to_nexus|lesson_event_ids"
tail -n 1 .nexus/knowledge/lesson_events.jsonl

echo -e "\n2. Testing Writeback Failure (Force Error in Python)..."
reset_state
python3 -c "import json; d=json.load(open('.ai/state.json')); d['state']='GEMINI_APPROVED'; json.dump(d, open('.ai/state.json', 'w'))"

# Modify lesson_writeback.sh to force fail
sed -i '' 's/persist_structured_lesson/non_existent_function/' gemini-codex-dual-gate/scripts/lib/lesson_writeback.sh

bash gemini-codex-dual-gate/scripts/codex_final_audit.sh
echo "Status: $?"
cat .ai/state.json | grep state

# Restore
git checkout gemini-codex-dual-gate/scripts/lib/lesson_writeback.sh
