#!/usr/bin/env bash
# Repro: security.yml (Bandit) and typecheck.yml (Pyright) impact steps only
# consider nexus/core/**. A PR adding shell=True to nexus/executors or
# nexus/orchestrator (the real execution sinks) is classified PASS without
# running Bandit. Logic copied verbatim from security.yml "Decide cheap exact-base impact".
set -euo pipefail
W=$(mktemp -d); cd "$W"; git init -q; git config user.email t@t; git config user.name t
mkdir -p nexus/executors nexus/core; echo 'x=1' > nexus/core/a.py; git add -A; git commit -qm base; BASE_SHA=$(git rev-parse HEAD)
cat > nexus/executors/cli_worker.py <<'PY'
import subprocess
def run(cmd): return subprocess.run(cmd, shell=True)
PY
git add -A; git commit -qm head; HEAD_SHA=$(git rev-parse HEAD)
REQUIRED="false"
git diff --quiet "$BASE_SHA" "$HEAD_SHA" -- pyproject.toml .bandit bandit.yaml uv.lock || REQUIRED=true
git diff --quiet "$BASE_SHA" "$HEAD_SHA" -- .github/workflows/security.yml || REQUIRED=true
git diff --quiet "$BASE_SHA" "$HEAD_SHA" -- scripts/ops/exact_base_tool_gate.py || REQUIRED=true
if [[ "$REQUIRED" != "true" ]] && git diff --name-only "$BASE_SHA" "$HEAD_SHA" -- 'nexus/core/*.py' 'nexus/core/**/*.py' | grep -q .; then REQUIRED=true; fi
echo "bandit required=$REQUIRED  -> classification: $( [ $REQUIRED = true ] && echo RUN || echo '{"classification":"PASS","reason":"no Bandit-impacted paths changed"}')"
if command -v bandit >/dev/null; then bandit -q -ll -ii nexus/executors/cli_worker.py | grep -E "Issue|B602" | head -2; fi
