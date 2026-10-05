#!/usr/bin/env bash
set -euo pipefail

# Nexus Core's repo-level completion verifier uses the repository's canonical
# fast L1 verification. Exact-base regression classification, trusted-anchor
# verification, and full-history secret scanning remain GitHub integration
# gates and are not reimplemented here.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

uv sync --frozen --all-groups --all-extras
uv pip install --python .venv/bin/python --requirement requirements/canonical-learning.txt
uv pip install --python .venv/bin/python --requirement requirements/canonical-runtime.txt

exec "$ROOT/scripts/ops/test_fast.sh"
