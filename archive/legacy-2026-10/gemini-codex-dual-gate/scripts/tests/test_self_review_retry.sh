#!/bin/bash
echo "=== Testing Self-Review Fail then Pass ==="
rm -rf .ai
bash gemini-codex-dual-gate/scripts/plan_with_codex.sh
bash gemini-codex-dual-gate/scripts/implement_from_plan.sh

# Force fail by adding 'todo'
echo "TODO: finish implementation" >> .ai/implementation-report.md
bash gemini-codex-dual-gate/scripts/gemini_self_review.sh

# Fix it
sed -i '' 's/TODO: finish implementation/Implementation complete/' .ai/implementation-report.md
bash gemini-codex-dual-gate/scripts/gemini_self_review.sh
bash gemini-codex-dual-gate/scripts/codex_final_audit.sh
cat .ai/state.json
