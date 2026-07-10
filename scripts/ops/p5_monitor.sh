#!/bin/bash
set -euo pipefail

LOG="/tmp/p5_monitor.log"
INSTR_DIR="/Users/jameschen/Downloads"
STATE="/tmp/p5_monitor_state"
INTERVAL=300

ORDER=(p5_i0 p5_f0 p5_i7 p5_i8 p5_i9 p5_v1 p5_v2 p5_v3 p5_v4 p5_c0 p5_e1 p5_e2 p5_e3 p5_e4 p5_e5 m1 p6_a0 ea_r0 ea_r1 ea_r2 ea_r3 ea_r4 ea_r5 ea_r6 ea_r7 ea_r8 ea_r9)

# Init state
if [ ! -f "$STATE" ]; then
  echo "last_commit=" > "$STATE"
  echo "current_idx=0" >> "$STATE"
  echo "last_instr=" >> "$STATE"
fi

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }

source "$STATE"
HEAD=$(git rev-parse HEAD 2>/dev/null || echo "")

if [ "$HEAD" = "$last_commit" ]; then
  exit 0  # no new commits → nothing to check
fi

# New commit found → check if it's P5-related
P5_COMMIT=$(git log "$last_commit..HEAD" --oneline --grep="P5-\|M1\|P6-A\|EA-R" 2>/dev/null | head -5 || true)

if [ -z "$P5_COMMIT" ]; then
  # No P5 commit, just update state and exit
  sed -i '' "s/^last_commit=.*/last_commit=$HEAD/" "$STATE"
  exit 0
fi

log "=== New P5 commits detected ==="
echo "$P5_COMMIT" >> "$LOG"

# Determine which instruction was just completed from the most recent P5 commit message
COMPLETED=""
for instr in "${ORDER[@]}"; do
  # Check if commit message matches this instruction (case insensitive)
  # Also check commit message patterns like "I0", "F0", etc.
  RAW="${instr#p5_}"
  RAW2="${RAW#p6_}"
  # Normalize: ea_r5 → ea-r5 so it matches EA-R5 in commit messages
  INSTR_PATTERN="${RAW2/_/-}"
  # Strip hash prefix to avoid hash substring matching (e.g. hash ee4e6 matching e4)
  COMMIT_MSG=$(echo "$P5_COMMIT" | head -1 | sed 's/^[0-9a-f]\{7,40\} //')
  if echo "$COMMIT_MSG" | rg -qi "$INSTR_PATTERN"; then
    COMPLETED="$instr"
    break
  fi
done

if [ -z "$COMPLETED" ]; then
  log "Could not determine which instruction was completed. P5 commits found but no match:"
  log "$P5_COMMIT"
  sed -i '' "s/^last_commit=.*/last_commit=$HEAD/" "$STATE"
  exit 0
fi

log "Completed: $COMPLETED"

# Find index of completed instruction
NEW_IDX=-1
for i in "${!ORDER[@]}"; do
  if [ "${ORDER[$i]}" = "$COMPLETED" ]; then
    NEW_IDX=$i
    break
  fi
done

if [ "$NEW_IDX" -lt 0 ]; then
  log "Unknown instruction, skipping"
  sed -i '' "s/^last_commit=.*/last_commit=$HEAD/" "$STATE"
  exit 0
fi

NEXT_IDX=$((NEW_IDX + 1))
if [ "$NEXT_IDX" -lt "${#ORDER[@]}" ]; then
  NEXT="${ORDER[$NEXT_IDX]}"
else
  NEXT="(none — last instruction)"
fi

log "Running tests for $COMPLETED..."
TEST_OUT=$(python3 -m pytest tests/unit/local_heal/test_p5_*.py -q 2>&1 || true)

if echo "$TEST_OUT" | rg -q "passed.*failed"; then
  FAIL_COUNT=$(echo "$TEST_OUT" | rg -o "[0-9]+ failed" | cut -d' ' -f1 || echo "0")
  PASS_COUNT=$(echo "$TEST_OUT" | rg -o "[0-9]+ passed" | cut -d' ' -f1 || echo "0")
  log "✗ $FAIL_COUNT failed, $PASS_COUNT passed"
  
  FAILED_NAMES=$(echo "$TEST_OUT" | rg "^FAILED " || true)
  log "Failed tests:"
  echo "$FAILED_NAMES" | while read -r line; do
    log "  ✗ $line"
  done
  
  # Append failure details to the next instruction file
  NEXT_FILE=$(ls "$INSTR_DIR/${NEXT}"*.md 2>/dev/null | head -1)
  if [ -n "$NEXT_FILE" ] && [ "$NEXT" != "(none"* ]; then
    log "→ Patching $NEXT_FILE with fix for $FAIL_COUNT test failure(s)"
    {
      echo ""
      echo "## ⚠️ Fixes required before starting this task"
      echo "The previous instruction ($COMPLETED) was committed but its test suite has failures."
      echo ""
      echo "### Failing tests"
      echo '```'
      echo "$FAILED_NAMES"
      echo '```'
      echo ""
      echo "### Test output summary"
      echo '```'
      echo "$TEST_OUT" | tail -20
      echo '```'
      echo ""
      echo "### Required fix before proceeding with this instruction"
      echo "1. Read the failing test output above and trace the root cause in the committed code."
      echo "2. Fix the bug in the previously committed P5 files (DO NOT skip — fix at source)."
      echo "3. Re-run the failing tests until green."
      echo "4. Amend or recommit the previous instruction if needed, then proceed."
    } >> "$NEXT_FILE"
    log "→ Appended fix block to $NEXT_FILE"
  fi
else
  PASS_COUNT=$(echo "$TEST_OUT" | rg -o "[0-9]+ passed" | cut -d' ' -f1 || echo "0")
  log "✓ All $PASS_COUNT passed"
fi

# Update state
sed -i '' "s/^last_commit=.*/last_commit=$HEAD/" "$STATE"
sed -i '' "s/^last_instr=.*/last_instr=$COMPLETED/" "$STATE"
sed -i '' "s/^current_idx=.*/current_idx=$NEW_IDX/" "$STATE"

log "State: completed=$COMPLETED, next=$NEXT, head=$HEAD"
log "=== Cycle complete ==="
