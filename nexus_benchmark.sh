#!/usr/bin/env bash
# ============================================================
# nexus_benchmark.sh — Canonical Nexus Benchmark Launcher (V5 Steel)
# 🛡️ [Hardening] This is the ONLY official entrypoint for benchmarks.
#
# Usage:
#   ./nexus_benchmark.sh --task "Fix #3111" --executor gemini --reviewer none
# ============================================================
set -euo pipefail

NEXUS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${NEXUS_ROOT}"
export NEXUS_BENCHMARK="1"

TASK=""
MODE="developer"
EXECUTOR="gemini"
REVIEWER="codex"
ISOLATED=""
FILES=()
SELF_TEST=""

# ── Argument Parsing ───────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --task)
            TASK="${2:-}"
            shift 2
            ;;
        --mode)
            MODE="${2:-}"
            shift 2
            ;;
        --executor)
            EXECUTOR="${2:-}"
            shift 2
            ;;
        --reviewer)
            REVIEWER="${2:-}"
            shift 2
            ;;
        --apply)
            APPLY="--apply"
            shift
            ;;
        --isolated)
            ISOLATED="--isolated"
            shift
            ;;
        --self-test)
            SELF_TEST="--self-test"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 --task '...' [--executor gemini|antigravity] [--reviewer codex|none] [--apply] [--isolated] [--self-test] [files...]"
            exit 0
            ;;
        *)
            FILES+=("$1")
            shift
            ;;
    esac
done

APPLY="${APPLY:-}"

# In self-test mode, task is not required
if [[ -z "$TASK" && -z "$SELF_TEST" ]]; then
    echo "❌ CLI_CONTRACT_ERROR: --task is required in benchmark mode." >&2
    exit 2
fi

# ── Launch ────────────────────────────────────────────────────
# Ensure valid MODE choices to return 2 if invalid (Legacy T3 requirement)
VALID_MODES="developer safe-commit agent-shield audit"
if ! echo "$VALID_MODES" | grep -qw "$MODE"; then
    echo "❌ CLI_CONTRACT_ERROR: --mode '$MODE' is not valid." >&2
    exit 2
fi

echo "🚀 [Launcher] Executing via Core Engine..."
if [[ -n "$SELF_TEST" ]]; then
    echo "   Mode:     SELF-TEST"
else
    echo "   Task:     ${TASK}"
fi
echo "   Executor: ${EXECUTOR}"
echo "   Reviewer: ${REVIEWER}"

# Handle empty FILES array safely under set -u
python3 "${NEXUS_ROOT}/scripts/codex_loop_brain.py" \
    ${FILES[@]+"${FILES[@]}"} \
    ${APPLY} \
    --benchmark \
    --mode "${MODE}" \
    --task "${TASK}" \
    --executor "${EXECUTOR}" \
    --reviewer "${REVIEWER}" \
    ${ISOLATED} \
    ${SELF_TEST}
