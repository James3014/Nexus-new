#!/bin/bash
# L2: 變更關聯層 (Impacted Verification)
set -e

CHANGED_PATH=$1

if [ -z "$CHANGED_PATH" ]; then
    echo "⚠️  No path provided. Running core smoke tests..."
    uv run python -m pytest tests/core tests/services/test_policy_gate.py -q
    exit 0
fi

echo "🔍 Analyzing impact for: $CHANGED_PATH"

TEST_TARGETS=""

if [[ $CHANGED_PATH == nexus/services/* ]]; then
    TEST_TARGETS="tests/services"
elif [[ $CHANGED_PATH == nexus/core/* ]]; then
    TEST_TARGETS="tests/core"
elif [[ $CHANGED_PATH == nexus/engine/* ]]; then
    TEST_TARGETS="tests/engine"
fi

if [ -n "$TEST_TARGETS" ]; then
    echo "🎯 [L2] Selected targets: $TEST_TARGETS"
    uv run python -m pytest $TEST_TARGETS -q
else
    echo "❓ No direct mapping for '$CHANGED_PATH'. Falling back to core smoke suite..."
    uv run python -m pytest tests/core tests/services/test_policy_gate.py -q
fi

echo "✅ [L2] Impacted verification complete."
