#!/bin/bash
# 🛡️ Nexus Wiki Fast-Feedback Pre-commit Hook
# Purpose: Prevent broken paths from being committed.

REPO_ROOT="$(git rev-parse --show-toplevel)"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"

echo "🔍 [Nexus-Wiki] Running Fast-Feedback Path Audit..."

# Run linter on changed files only
"${VENV_PYTHON}" "${REPO_ROOT}/scripts/ops/wiki_linter.py" --changed-only
RESULT_LINTER=$?

# Run Agent Protocol Check on staged files
echo "🔍 [Nexus-Protocol] Running Staged Boundary Audit..."
"${VENV_PYTHON}" "${REPO_ROOT}/scripts/ops/agent_protocol_check.py" --check-staged --strict-boundary
RESULT_PROTOCOL=$?

if [ $RESULT_LINTER -ne 0 ] || [ $RESULT_PROTOCOL -ne 0 ]; then
    echo "❌ [Nexus-Gate] Pre-commit Audit FAILED."
    if [ $RESULT_LINTER -ne 0 ]; then echo "  - Wiki Linter FAILED"; fi
    if [ $RESULT_PROTOCOL -ne 0 ]; then echo "  - Agent Protocol Check FAILED"; fi
    exit 1
fi

echo "✅ [Nexus-Gate] Pre-commit Audit PASSED."
exit 0
