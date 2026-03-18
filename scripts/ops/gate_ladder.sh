#!/bin/zsh
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
MINI_TASKS="${NEXUS_MINI_TASKS:-3}"

cd "$REPO_ROOT"

echo "== L0: scope + write-path + focused guards =="
uv run python scripts/ops/scope_guard.py
uv run python scripts/ops/write_path_smoke.py
uv run pytest -q tests/test_ci_gate_phantom_guard.py tests/test_phantom_success_guards.py

echo "== L1: mini benchmark (${MINI_TASKS} tasks) =="
uv run scripts/nexus_cli.py nexus:benchmark --tasks "$MINI_TASKS" --output ci_benchmark_mini.csv

echo "== L2: full ci_gate =="
uv run scripts/ops/ci_gate.py

echo "✅ GATE_LADDER PASS"
