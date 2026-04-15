#!/bin/bash
set -euo pipefail

# Generate a single source-of-truth startup briefing that forces
# task classification + Learn/Hyper/NightShift routing discipline.

OUT_FILE="${1:-.nexus/reports/enforced_agent_briefing.md}"
mkdir -p "$(dirname "$OUT_FILE")"

cat > "$OUT_FILE" <<'EOF'
[NEXUS v24 ACTIVE]

# Startup Contract (Enforced)
1. Classify task first: `feature` / `bugfix` / `run`.
2. Then choose strategy: default `Learn+Hyper`, escalate to `NightShift` only when required.
3. Never claim done before gates.

# Routing Mini-Rules (Mandatory)
1. Learn first for unknown domains/repos:
   - `uv run scripts/engine/nexus_cli.py nexus learn:ingest --source "<URL_OR_REPO>" --topic "<TOPIC>"`
   - `uv run scripts/engine/nexus_cli.py nexus learn:converge --topic "<TOPIC>" --max-rounds 2 --question-count 5 --pass-threshold 0.6 --swarm-mode --swarm-max-parallel 3`
2. Default path is Hyper:
   - `uv run scripts/engine/nexus_cli.py nexus research:auto-flow --task "<TASK_DESC>" --target-file "<TARGET_FILE>" --test-file "<TEST_FILE>" --explain-route`
3. Escalate to NightShift only if any condition hits:
   - Hyper failed 2 times
   - `stage1_no_passing_candidate`
   - cross-module high-risk concurrency/timing/root-cause-unknown
4. NightShift command:
   - `uv run python scripts/nightshift.py --task "<TASK_DESC>" --target_file "<TARGET_FILE>" --max_rounds 3 --budget_min 3 --convergence_patience 2 --model gemini-3.1-pro-preview --fallback-model gemini-3-flash-preview`
5. Gates (must pass):
   - `uv run scripts/engine/nexus_cli.py nexus acceptance-check`
   - `uv run scripts/engine/nexus_cli.py nexus contract-check --contract-file .nexus/config/task_contract.example.json`

# Notes
- Prioritize quality metrics over speed: success_rate + regression_rate first.
- Hyper can be slightly slower than baseline but must not be less stable.
EOF

echo "$OUT_FILE"
