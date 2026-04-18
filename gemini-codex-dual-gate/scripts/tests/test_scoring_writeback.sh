#!/bin/bash
echo "=== Testing Dual-Model Scoring & Writeback ==="

reset_state() {
  rm -rf .ai nexus_wiki_vault
  mkdir -p .ai
  cp gemini-codex-dual-gate/templates/.ai/state.json .ai/state.json
  python3 -c "import json; d=json.load(open('.ai/state.json')); d['state']='GEMINI_APPROVED'; json.dump(d, open('.ai/state.json', 'w'))"
  echo "# Acceptance" > .ai/acceptance.md
  echo "- AC-1: Pass" >> .ai/acceptance.md
  echo "# Test Results" > .ai/test-results.md
  echo "## Summary\n## Details" >> .ai/test-results.md
}

echo "1. Simulating REVISE with Lessons..."
reset_state
# Mock codex output for REVISE
export MOCK_OUTPUT="AUDIT: REVISE
overall: 70
PLAN_CONFORMANCE: PASS
ACCEPTANCE_COVERAGE:
  - AC-1: FAIL (evidence: ...)
FINDINGS:
  - [HIGH] Missing error handling
REQUIRED_LESSONS:
  - Always implement try-catch for network calls."

# Temporary alias/mock to simulate codex
codex() { echo "$MOCK_OUTPUT"; }
export -f codex
bash gemini-codex-dual-gate/scripts/codex_final_audit.sh
echo "--- Lessons in Wiki ---"
cat nexus_wiki_vault/Learning_Closure_Matrix.md
cat .ai/state.json | grep -E "score|lessons"

echo -e "\n2. Simulating PASS..."
reset_state
export MOCK_OUTPUT="AUDIT: PASS
overall: 95
PLAN_CONFORMANCE: PASS
ACCEPTANCE_COVERAGE:
  - AC-1: PASS (evidence: ...)
FINDINGS:
  - [LOW] Minor typo
REQUIRED_LESSONS:
  - None"
bash gemini-codex-dual-gate/scripts/codex_final_audit.sh
cat .ai/state.json | grep -E "score|lessons"
