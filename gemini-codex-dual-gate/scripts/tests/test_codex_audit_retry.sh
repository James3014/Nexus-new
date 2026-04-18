#!/bin/bash
echo "=== Testing Codex Audit Fail then Revise ==="
rm -rf .ai
bash gemini-codex-dual-gate/scripts/plan_with_codex.sh
bash gemini-codex-dual-gate/scripts/implement_from_plan.sh
bash gemini-codex-dual-gate/scripts/gemini_self_review.sh

# Force fail by adding 'fail' to test results
echo "Tests failed: regression in core" >> .ai/test-results.md
bash gemini-codex-dual-gate/scripts/codex_final_audit.sh

# Fix it
echo "All tests passed" > .ai/test-results.md
bash gemini-codex-dual-gate/scripts/codex_final_audit.sh
cat .ai/state.json
