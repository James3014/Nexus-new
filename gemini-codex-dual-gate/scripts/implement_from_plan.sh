#!/bin/bash
source "$(dirname "$0")/lib/state.sh"
source "$(dirname "$0")/lib/artifact.sh"

STATE=$(read_state | python3 -c "import json, sys; print(json.load(sys.stdin)['state'])")

if [ "$STATE" != "PLAN_APPROVED" ]; then
  echo "❌ Error: Plan is not approved. Current state: $STATE"
  exit 1
fi

# 1. Check Plan Drift
OLD_HASH=$(read_state | python3 -c "import json, sys; print(json.load(sys.stdin)['plan_hash'])")
NEW_HASH=$(calculate_hash ".ai/plan.md")

if [ "$OLD_HASH" != "$NEW_HASH" ]; then
  update_state "plan_drift" "true"
  set_status "PLAN_DRIFT_DETECTED"
  echo "❌ Error: Plan drift detected. Hash changed. Please re-run /plan-with-codex."
  exit 1
fi

# 2. Implementation Simulation
echo "🚀 Implementing from plan..."
generate_changed_files
cp "$(dirname "$0")/../templates/.ai/implementation-report.md" .ai/implementation-report.md
cp "$(dirname "$0")/../templates/.ai/test-results.md" .ai/test-results.md

set_status "IMPLEMENTING"
echo "✅ Implementation artifacts generated. Ready for /gemini-self-review."
