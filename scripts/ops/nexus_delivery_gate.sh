#!/bin/zsh
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$REPO_ROOT"

EVIDENCE_PATH=".nexus/reports/hallucination_evidence.json"
RECEIPT_PATH=".nexus/reports/delivery_gate.json"
BASELINE_PATH=".nexus/reports/baseline/baseline_manifest.json"

echo "[delivery-gate] Canonical Flow v24.1 Initiated"

# --- STEP 1: Integrity (File Check) ---
echo "== Step 1: Integrity (Evidence Check) =="
if [[ ! -f "$EVIDENCE_PATH" ]]; then
  echo "❌ [FAIL] Missing evidence file: $EVIDENCE_PATH" >&2
  exit 1
fi

# --- STEP 2: Anti-Drift ---
echo "== Step 2: Anti-Drift (Governance Seal) =="
if ! python3 scripts/ops/verify_governance_seal.py; then
  echo "❌ [FAIL] Governance drift detected!" >&2
  exit 11
fi

# --- STEP 3: Lineage ---
echo "== Step 3: Lineage (Chain Verification) =="
if ! python3 scripts/ops/verify_lineage_chain.py; then
  echo "❌ [FAIL] Lineage chain broken!" >&2
  exit 12
fi

# --- STEP 4: Evidence Verifier (Replay) ---
echo "== Step 4: Evidence Verifier (Replay) =="
if ! python3 scripts/ops/evidence_verifier.py "$EVIDENCE_PATH"; then
  echo "❌ [FAIL] Evidence verification failed (Replay/Hallucination rejection)!" >&2
  exit 13
fi

# --- STEP 5: Tests ---
echo "== Step 5: Tests (Orchestrator Regression) =="
if ! uv run pytest -q tests/nexus/orchestrator; then
  echo "❌ [FAIL] Functional tests failed!" >&2
  exit 14
fi

# --- STEP 6: Regression Metrics ---
echo "== Step 6: Regression Metrics (Performance/Health) =="
if ! python3 scripts/ops/diagnose_regression.py; then
  echo "❌ [FAIL] Regression metrics below baseline!" >&2
  exit 15
fi

# --- STEP 7: Acceptance ---
echo "== Step 7: Acceptance (System Gate) =="
if ! uv run scripts/engine/nexus_cli.py nexus acceptance-check --json --evidence "$EVIDENCE_PATH"; then
  echo "❌ [FAIL] Final acceptance check rejected!" >&2
  exit 16
fi

# --- STEP 8: Final Receipt & Lineage Append ---
echo "== Step 8: Receipt & Final Integrity =="

python3 - <<'PY' "$RECEIPT_PATH" "$EVIDENCE_PATH"
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

receipt_path = Path(sys.argv[1])
evidence_path = Path(sys.argv[2])

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

branch = subprocess.check_output(["git", "branch", "--show-current"]).decode().strip()
head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()

payload = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "version": "v24.1-canonical",
    "branch": branch,
    "head": head,
    "steps": [
        {"name": "integrity", "exit_code": 0},
        {"name": "anti_drift", "exit_code": 0, "command": "verify_governance_seal.py"},
        {"name": "lineage", "exit_code": 0, "command": "verify_lineage_chain.py"},
        {"name": "verifier", "exit_code": 0, "command": "evidence_verifier.py"},
        {"name": "tests", "exit_code": 0, "command": "pytest tests/nexus/orchestrator"},
        {"name": "regression", "exit_code": 0, "command": "diagnose_regression.py"},
        {"name": "acceptance", "exit_code": 0, "command": "acceptance-check"}
    ],
    "artifacts": {
        "evidence": {"path": str(evidence_path), "sha256": sha256(evidence_path)},
        "baseline": {"path": ".nexus/reports/baseline/baseline_manifest.json", "sha256": sha256(Path(".nexus/reports/baseline/baseline_manifest.json"))}
    },
    "delivery_gate_passed": True
}
receipt_path.parent.mkdir(parents=True, exist_ok=True)
receipt_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY

echo "[delivery-gate] appending lineage node..."
python3 scripts/ops/append_lineage.py "delivery_gate_receipt" "$(cat $RECEIPT_PATH)"

echo "[delivery-gate] PASS"
