#!/bin/bash
echo "=== Testing High-Bar Gate Scenarios ==="

reset_state() {
  rm -rf .ai
  mkdir -p .ai
  cp gemini-codex-dual-gate/templates/.ai/state.json .ai/state.json
  python3 -c "import json; d=json.load(open('.ai/state.json')); d['state']='GEMINI_APPROVED'; json.dump(d, open('.ai/state.json', 'w'))"
}

echo "1. Testing Missing AC numbering..."
reset_state
echo "# Acceptance" > .ai/acceptance.md
echo "- This should fail" >> .ai/acceptance.md
bash gemini-codex-dual-gate/scripts/codex_final_audit.sh
cat .ai/state.json | grep state

echo -e "\n2. Testing Missing Test Details..."
reset_state
echo "# Acceptance" > .ai/acceptance.md
echo "- AC-1: Pass" >> .ai/acceptance.md
echo "# Test Results" > .ai/test-results.md
echo "No summary or details" >> .ai/test-results.md
bash gemini-codex-dual-gate/scripts/codex_final_audit.sh
cat .ai/state.json | grep state

echo -e "\n3. Testing Valid Structure (Proceeds to Codex)..."
reset_state
echo "# Acceptance" > .ai/acceptance.md
echo "- AC-1: Pass" >> .ai/acceptance.md
echo "# Test Results" > .ai/test-results.md
echo "## Summary" >> .ai/test-results.md
echo "## Details" >> .ai/test-results.md
bash gemini-codex-dual-gate/scripts/codex_final_audit.sh
