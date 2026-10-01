#!/usr/bin/env bash
# Canonical impacted (L2) verification. Targets are always passed as an argv
# array; an empty invocation explicitly uses the documented core fallback.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1
: "${UV_CACHE_DIR:="$ROOT/.tmp/uv-cache"}"
export UV_CACHE_DIR
if [[ "${NEXUS_TEST_FORCE_UV:-0}" != 1 && -x .venv/bin/python ]]; then
  SELECTOR=(.venv/bin/python scripts/ops/select_tests.py)
  PYTEST=(.venv/bin/python -m pytest)
else
  SELECTOR=(uv run python scripts/ops/select_tests.py)
  PYTEST=(uv run python -m pytest)
fi
OPTIONAL_EXCLUSION=tests/core/test_web_dom_mapper.py

if (( $# == 0 )); then
  echo "[L2] no changed paths; using documented core fallback"
  exec "$ROOT/scripts/ops/test_fast.sh"
fi

for path in "$@"; do
  if [[ ! -e "$path" ]]; then
    echo "[L2] changed path is missing: $path" >&2
    exit 2
  fi
done

selection="$("${SELECTOR[@]}" "$@")"
if [[ -z "${selection//[[:space:]]/}" ]]; then
  echo "[L2] selector returned no targets; refusing empty success" >&2
  exit 2
fi
if [[ "$selection" == *$'\n'* ]]; then
  echo "[L2] selector returned multiple target lines; refusing ambiguous selection" >&2
  exit 2
fi
read -r -a targets <<< "$selection"
if (( ${#targets[@]} == 0 )); then
  echo "[L2] selector returned no targets; refusing empty success" >&2
  exit 2
fi
for target in "${targets[@]}"; do
  if [[ ! -e "$target" ]]; then
    echo "[L2] selected target is missing: $target" >&2
    exit 2
  fi
done
pytest_args=("${targets[@]}")
for target in "${targets[@]}"; do
  if [[ "$target" == "tests/core" ]]; then
    if [[ ! -e "$OPTIONAL_EXCLUSION" ]]; then
      echo "[L2] missing declared optional exclusion: $OPTIONAL_EXCLUSION" >&2
      exit 2
    fi
    printf '[L2] excluded target: %s (requires browser extra; covered by full)\n' "$OPTIONAL_EXCLUSION"
    pytest_args+=(--ignore="$OPTIONAL_EXCLUSION")
    break
  fi
done
printf '[L2] selected targets: %s\n' "${targets[*]}"
"${PYTEST[@]}" "${pytest_args[@]}" -q
