#!/bin/bash
echo "=== Testing Happy Path ==="
rm -rf .ai
bash gemini-codex-dual-gate/scripts/plan_with_codex.sh
bash gemini-codex-dual-gate/scripts/implement_from_plan.sh
bash gemini-codex-dual-gate/scripts/gemini_self_review.sh
bash gemini-codex-dual-gate/scripts/codex_final_audit.sh
cat .ai/state.json
