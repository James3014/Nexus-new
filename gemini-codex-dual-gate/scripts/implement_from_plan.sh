#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/lib/state.sh"
source "$(dirname "$0")/lib/artifact.sh"

STATE=$(read_state | python3 -c "import json, sys; print(json.load(sys.stdin)['state'])")

if [ "$STATE" != "PLAN_APPROVED" ] && [ "$STATE" != "PLAN_APPROVED_WITH_RISK" ]; then
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

# 2. Artifact Completeness
if ! check_artifacts; then
  echo "❌ Missing required artifacts."
  exit 1
fi

# 3. Real implementation evidence only
if ! has_real_changes; then
  set_status "BLOCKED"
  echo "❌ No real code changes detected (staged/unstaged)."
  exit 1
fi
generate_changed_files

if [ ! -f .ai/implementation-report.md ]; then
  set_status "BLOCKED"
  echo "❌ Missing .ai/implementation-report.md."
  exit 1
fi

# 4. Execute real tests and persist output
run_test_commands_or_fail

set_status "IMPLEMENTING"
echo "✅ Implementation evidence and test outputs recorded. Ready for /gemini-self-review."
