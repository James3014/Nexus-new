#!/bin/bash
# L2: 變更關聯層 (Impacted Verification)
set -e

CHANGED_PATHS=("$@")

if [ ${#CHANGED_PATHS[@]} -eq 0 ]; then
    echo "⚠️  No path provided. Running core smoke tests..."
    uv run python -m pytest tests/core tests/services/test_policy_gate.py -q
    exit 0
fi

echo "🔍 Analyzing impact for: ${CHANGED_PATHS[*]}"

TEST_TARGETS=$(uv run python scripts/ops/select_tests.py "${CHANGED_PATHS[@]}")

echo "🎯 [L2] Selected targets: $TEST_TARGETS"
uv run python -m pytest $TEST_TARGETS -q

echo "✅ [L2] Impacted verification complete."
