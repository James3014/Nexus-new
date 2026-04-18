#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/lib/state.sh"

echo "⛓️ Initiating Closed-Loop Implementation..."

# 0. Plan Gate
STATE=$(python3 -c "import json; print(json.load(open('.ai/state.json'))['state'])" 2>/dev/null || echo "INIT")
if [ "$STATE" != "PLAN_APPROVED" ]; then
  if [ "$STATE" = "PLAN_APPROVED_WITH_RISK" ]; then
    echo "📐 Plan approved with risk (quota skip). Proceeding with risk flag."
  else
  echo "📐 Plan is not approved yet ($STATE). Running plan gate first..."
  bash "$(dirname "$0")/plan_with_codex.sh"
  fi
fi

# 1. Implementation
bash "$(dirname "$0")/implement_from_plan.sh"
if [ $? -ne 0 ]; then echo "❌ Implementation Step Failed."; exit 1; fi

# 2. Gemini Self-Review (Gate 1)
bash "$(dirname "$0")/gemini_self_review.sh"
STATE=$(read_state | python3 -c "import json, sys; print(json.load(sys.stdin)['state'])")
if [ "$STATE" == "REVISING_IMPLEMENTATION" ] || [ "$STATE" == "BLOCKED" ]; then
    echo "⚠️ Gate 1 (Gemini) stopped the loop. Check .ai/gemini-scorecard.md"
    exit 1
fi

# 3. Codex Final Audit (Gate 2)
bash "$(dirname "$0")/codex_final_audit.sh"
STATE=$(read_state | python3 -c "import json, sys; print(json.load(sys.stdin)['state'])")
if [ "$STATE" == "DONE" ]; then
    echo "🎉 CLOSED-LOOP SUCCESS: Codex has audited and passed the implementation."
    exit 0
elif [ "$STATE" == "DONE_WITH_RISK" ]; then
    echo "⚠️ CLOSED-LOOP PARTIAL: quota skip occurred; not merge-ready."
    exit 0
else
    echo "⚠️ Gate 2 (Codex) stopped the loop. Check .ai/codex-scorecard.md"
    exit 1
fi
