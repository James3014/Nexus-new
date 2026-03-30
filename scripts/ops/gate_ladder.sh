#!/bin/zsh
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
MINI_TASKS="${NEXUS_MINI_TASKS:-3}"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
MIGRATION_SCOPE_FLAG="${NEXUS_MIGRATION_CHECK_SCOPE:-0}"

cd "$REPO_ROOT"

echo "== L0: scope + write-path + focused guards =="
"$VENV_PYTHON" scripts/ops/scope_guard.py
"$VENV_PYTHON" scripts/ops/write_path_smoke.py
"$VENV_PYTHON" -m pytest -q tests/test_ci_gate_phantom_guard.py tests/test_phantom_success_guards.py

echo "== L0.5: migration safety validator =="
if [[ "$MIGRATION_SCOPE_FLAG" == "1" ]]; then
  "$VENV_PYTHON" scripts/core/migration_safety_validator.py --check-scope-guard
else
  "$VENV_PYTHON" scripts/core/migration_safety_validator.py
fi

echo "== L1: mini benchmark (${MINI_TASKS} tasks) =="
"$VENV_PYTHON" scripts/nexus_cli.py nexus:benchmark --tasks "$MINI_TASKS" --output ci_benchmark_mini.csv

echo "== L2: full ci_gate =="
"$VENV_PYTHON" scripts/ops/ci_gate.py

if [[ -n "${NEXUS_COMPLETION_TASK_NAME:-}" ]]; then
  echo "== L3: completion gate =="
  completion_args=(
    --task-name "${NEXUS_COMPLETION_TASK_NAME}"
    --task-level "${NEXUS_COMPLETION_TASK_LEVEL:-feature}"
  )
  if [[ -n "${NEXUS_COMPLETION_VERIFY_FILE:-}" ]]; then
    completion_args+=(--verify-file "${NEXUS_COMPLETION_VERIFY_FILE}")
  fi
  if [[ -n "${NEXUS_COMPLETION_ARTIFACT_FILE:-}" ]]; then
    completion_args+=(--artifact-file "${NEXUS_COMPLETION_ARTIFACT_FILE}")
  fi
  "$VENV_PYTHON" scripts/ops/nexus_completion_gate.py "${completion_args[@]}"
fi

echo "✅ GATE_LADDER PASS"
