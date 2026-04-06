#!/bin/bash
# 🛡️ Nexus Wiki Fast-Feedback Pre-commit Hook
# Purpose: Prevent broken paths from being committed.

REPO_ROOT="$(git rev-parse --show-toplevel)"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"

echo "🔍 [Nexus-Wiki] Running Fast-Feedback Path Audit..."

# Run linter on changed files only
"${VENV_PYTHON}" "${REPO_ROOT}/scripts/ops/wiki_linter.py" --changed-only

RESULT=$?

if [ $RESULT -ne 0 ]; then
    echo "❌ [Nexus-Wiki] Path Audit FAILED. Please fix invalid paths before committing."
    exit 1
fi

echo "✅ [Nexus-Wiki] Path Audit PASSED."
exit 0
