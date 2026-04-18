#!/bin/zsh
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$REPO_ROOT"

EVIDENCE_PATH=".nexus/reports/hallucination_evidence.json"
ALLOW_DIRTY_CONFIG=".nexus/config/delivery_gate_allow_dirty.json"
RECEIPT_PATH=".nexus/reports/delivery_gate.json"
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
    --receipt)
      RECEIPT_PATH="${2:?missing value for --receipt}"
      shift 2
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
  --ignore-dirty-config "$ALLOW_DIRTY_CONFIG" \
  --json

if [[ "$RUN_ROUTER_BENCH" == "1" && -f "scripts/ops/router_policy_benchmark.py" ]]; then
  echo "== Delivery Gate: router benchmark =="
  python3 scripts/ops/router_policy_benchmark.py
fi

python3 - <<'PY' "$RECEIPT_PATH" "$EVIDENCE_PATH"
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

receipt_path = Path(sys.argv[1])
evidence_path = Path(sys.argv[2])
acceptance_path = Path(".nexus/reports/acceptance_check.json")

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

branch = subprocess.check_output(["git", "branch", "--show-current"]).decode().strip()
head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
payload = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "branch": branch,
    "head": head,
    "delivery_gate_passed": True,
    "acceptance_report_path": str(acceptance_path),
    "acceptance_report_sha256": sha256(acceptance_path),
    "evidence_path": str(evidence_path),
    "evidence_sha256": sha256(evidence_path),
    "tests_command": "uv run pytest -q tests/nexus/orchestrator",
    "tests_exit_code": 0,
    "acceptance_command": f"uv run scripts/engine/nexus_cli.py nexus acceptance-check --json --evidence {evidence_path}",
    "acceptance_exit_code": 0,
    "report_integrity_command": "uv run scripts/ops/verify_report_claims.py --project-root . --require-acceptance-pass --require-clean --ignore-dirty-config .nexus/config/delivery_gate_allow_dirty.json --json",
    "report_integrity_exit_code": 0,
}
receipt_path.parent.mkdir(parents=True, exist_ok=True)
receipt_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY

echo "[delivery-gate] receipt=$RECEIPT_PATH"

echo "[delivery-gate] PASS"
