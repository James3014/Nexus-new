#!/usr/bin/env bash
# Canonical fast (L1) repository verification.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1
: "${UV_CACHE_DIR:="$ROOT/.tmp/uv-cache"}"
export UV_CACHE_DIR
if [[ "${NEXUS_TEST_FORCE_UV:-0}" != 1 && -x .venv/bin/python ]]; then PYTEST=(.venv/bin/python -m pytest); else PYTEST=(uv run python -m pytest); fi
TARGETS=(tests/core tests/services/test_policy_gate.py)
OPTIONAL_EXCLUSION=tests/core/test_web_dom_mapper.py

for target in "${TARGETS[@]}"; do
  if [[ ! -e "$target" ]]; then
    echo "[L1] missing test target: $target" >&2
    exit 2
  fi
done
if [[ ! -e "$OPTIONAL_EXCLUSION" ]]; then
  echo "[L1] missing declared optional exclusion: $OPTIONAL_EXCLUSION" >&2
  exit 2
fi
printf '[L1] selected targets: %s\n' "${TARGETS[*]}"
printf '[L1] excluded target: %s (requires browser extra; covered by full)\n' "$OPTIONAL_EXCLUSION"
"${PYTEST[@]}" "${TARGETS[@]}" --ignore="$OPTIONAL_EXCLUSION" -m 'not slow' -q --maxfail=3
