#!/usr/bin/env bash
# Single, explicit repository test command matrix.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1
: "${UV_CACHE_DIR:="$ROOT/.tmp/uv-cache"}"
export UV_CACHE_DIR
if [[ "${NEXUS_TEST_FORCE_UV:-0}" != 1 && -x .venv/bin/python ]]; then PYTHON=(.venv/bin/python); else PYTHON=(uv run python); fi
usage() {
  echo "usage: $0 {environment|fast|changed|full|lint|fixture} [args...]" >&2
}
if (( $# == 0 )); then usage; exit 2; fi
mode="$1"; shift
case "$mode" in
  environment|env)
    (( $# == 0 )) || { echo "environment takes no arguments" >&2; exit 2; }
    exec bash scripts/ops/_nexus_preflight.sh
    ;;
  fast) (( $# == 0 )) || { echo "fast takes no arguments" >&2; exit 2; }; exec bash scripts/ops/test_fast.sh ;;
  changed|impacted) exec bash scripts/ops/test_changed.sh "$@" ;;
  full)
    if [[ "${NEXUS_ALLOW_FULL:-0}" != 1 && "${1:-}" != "--confirm-full" ]]; then
      echo "full regression is an escalation; re-run with --confirm-full (or NEXUS_ALLOW_FULL=1)" >&2; exit 2
    fi
    if [[ "${1:-}" == "--confirm-full" ]]; then shift; fi
    (( $# == 0 )) || { echo "full accepts only --confirm-full" >&2; exit 2; }
    targets=(tests)
    [[ -d tests ]] || { echo "missing test path: tests" >&2; exit 2; }
    echo "[FULL] selected targets: tests"
    exec "${PYTHON[@]}" -m pytest "${targets[@]}" -x -v --timeout=300
    ;;
  lint)
    files=("$@")
    if (( ${#files[@]} == 0 )); then files=(tests/ops/test_repo_test_commands.py); fi
    for file in "${files[@]}"; do
      if [[ "$file" == -* || ! -f "$file" ]]; then
        echo "lint target must be an existing file (not an option): $file" >&2
        exit 2
      fi
    done
    echo "[LINT] selected targets: ${files[*]}"
    if [[ "${NEXUS_TEST_FORCE_UV:-0}" != 1 && -x .venv/bin/ruff ]]; then RUFF=(.venv/bin/ruff); else RUFF=(uv run ruff); fi
    exec "${RUFF[@]}" check "${files[@]}"
    ;;
  fixture)
    (( $# == 0 )) || { echo "fixture takes no arguments" >&2; exit 2; }
    exec "${PYTHON[@]}" scripts/ci/run_swebench_subset.py --mode smoke
    ;;
  *) echo "unsupported mode: $mode" >&2; usage; exit 2 ;;
esac
