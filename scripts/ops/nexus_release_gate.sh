#!/bin/zsh
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"

cd "$REPO_ROOT"

echo "== Release Gate: base ladder =="
scripts/ops/gate_ladder.sh


echo "== Release Gate: acceptance check =="
uv run scripts/engine/nexus_cli.py nexus delivery-gate --evidence .nexus/reports/hallucination_evidence.json

echo "== Release Gate: completion gate =="
uv run python scripts/ops/nexus_completion_gate.py "$@"
