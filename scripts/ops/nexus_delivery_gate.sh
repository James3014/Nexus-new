#!/bin/zsh
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$REPO_ROOT"

EVIDENCE_PATH=".nexus/reports/hallucination_evidence.json"
RUN_ROUTER_BENCH=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --evidence)
      EVIDENCE_PATH="${2:?missing value for --evidence}"
      shift 2
      ;;
    --router-benchmark)
      RUN_ROUTER_BENCH=1
      shift
      ;;
    *)
      echo "[delivery-gate] unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$EVIDENCE_PATH" ]]; then
  echo "[delivery-gate] missing evidence file: $EVIDENCE_PATH" >&2
  exit 1
fi

echo "[delivery-gate] pwd=$(pwd)"
echo "[delivery-gate] branch=$(git branch --show-current)"
echo "[delivery-gate] head=$(git rev-parse --short HEAD)"

echo "== Delivery Gate: tests =="
uv run pytest -q tests/nexus/orchestrator

echo "== Delivery Gate: acceptance =="
uv run scripts/engine/nexus_cli.py nexus acceptance-check --json --evidence "$EVIDENCE_PATH"

echo "== Delivery Gate: report integrity =="
uv run scripts/ops/verify_report_claims.py \
  --project-root . \
  --require-acceptance-pass \
  --require-clean \
  --ignore-dirty-path .nexus/reports/acceptance_check.json \
  --ignore-dirty-path .nexus/reports/acceptance_check.md \
  --json

if [[ "$RUN_ROUTER_BENCH" == "1" && -f "scripts/ops/router_policy_benchmark.py" ]]; then
  echo "== Delivery Gate: router benchmark =="
  python3 scripts/ops/router_policy_benchmark.py
fi

echo "[delivery-gate] PASS"
