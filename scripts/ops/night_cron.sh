#!/bin/bash
# 🌙 Nexus Night Shift Automation Runner (L1)
# Usage: ./scripts/ops/night_cron.sh [task_limit]

LIMIT=${1:-10}
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
CSV_OUT="ci_benchmark_night_${TIMESTAMP}.csv"
SUMMARY_OUT="docs/reports/night_shift_${TIMESTAMP}.md"

echo "🚀 [NightShift] Starting Benchmark (Tasks: $LIMIT)..."
uv run scripts/engine/nexus_cli.py nexus:benchmark --tasks $LIMIT --output $CSV_OUT

echo "📊 [NightShift] Generating Summary..."
uv run python3 scripts/ops/night_summary.py $CSV_OUT $SUMMARY_OUT

echo "💎 [NightShift:L2] Crystallizing new policies..."
uv run python3 scripts/ops/crystal_factory.py

echo "🛡️ [NightShift:L2] Checking for review proposals..."
# Always offer review if there are staged changes
if [[ $(git diff --staged --name-only) ]]; then
    uv run python3 scripts/ops/review_proposal.py
fi

echo "✅ [NightShift] Done. Report saved to: $SUMMARY_OUT"
# Optional: say "Night Shift complete" using Mac voice
# say "Nexus night shift complete"
