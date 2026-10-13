#!/usr/bin/env bash
# Build (idempotently) the canonical dependency material environment and print
# its python path on stdout. All tool output goes to stderr so callers can
# capture the path with command substitution.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_DIR="${HOME:?HOME must be set}/nexus-core-materials"
PY="$ENV_DIR/bin/python"
MARK="$ENV_DIR/.nexus-core-materials-ready"

if [ ! -x "$PY" ] || [ ! -f "$MARK" ]; then
  rm -rf "$ENV_DIR"
  uv venv --python 3.11 "$ENV_DIR" >&2
  uv pip install --python "$PY" --requirement "$ROOT/requirements/canonical-learning.txt" >&2
  uv pip install --python "$PY" --requirement "$ROOT/requirements/canonical-runtime.txt" >&2
  : > "$MARK"
fi
printf '%s\n' "$PY"
