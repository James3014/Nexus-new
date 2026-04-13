#!/bin/bash
# L3: 全量回歸層 (Full Regression)
set -e
echo "⚠️  CRITICAL: DO NOT run other pytest instances simultaneously!"
echo "🔥 [L3] Running full regression suite..."
uv run python -m pytest -q > /tmp/full_test_result.txt 2>&1 || (tail -n 20 /tmp/full_test_result.txt && exit 1)
echo "----------------------------------------"
echo "📊 TEST SUMMARY:"
grep -E "passed|failed|warnings" /tmp/full_test_result.txt | tail -n 1
echo "----------------------------------------"
echo "🏆 [L3] Full regression passed."
