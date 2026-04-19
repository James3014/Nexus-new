#!/bin/zsh
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$REPO_ROOT"

EVIDENCE_PATH=".nexus/reports/hallucination_evidence.json"
RECEIPT_PATH=".nexus/reports/delivery_gate.json"
BASELINE_PATH=".nexus/reports/baseline/baseline_manifest.json"
ACCEPTANCE_REPORT_PATH=".nexus/reports/acceptance_check.json"
ACCEPTANCE_POLICY="${NEXUS_ACCEPTANCE_POLICY:-dev}" # dev | prod

echo "[delivery-gate] Canonical Flow v24.1 Initiated"
echo "[delivery-gate] acceptance_policy=${ACCEPTANCE_POLICY}"

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

# --- STEP 7: Integrity Claims ---
echo "== Step 7: Integrity Claims (Report/Context Truth) =="
if ! uv run scripts/ops/verify_report_claims.py \
  --json \
  --ignore-dirty-config .nexus/config/delivery_gate_allow_dirty.json \
  --baseline-manifest "$BASELINE_PATH"; then
  echo "❌ [FAIL] Report integrity check failed!" >&2
  exit 17
fi

# --- STEP 8: Acceptance Quality ---
echo "== Step 8: Acceptance (Quality Gate) =="
set +e
uv run scripts/engine/nexus_cli.py nexus acceptance-check --json --evidence "$EVIDENCE_PATH"
ACC_RC=$?
set -e

ACC_STATUS="UNKNOWN"
ACC_GATE="false"
ACC_PRIMARY="acceptance_report_missing"
if [[ -f "$ACCEPTANCE_REPORT_PATH" ]]; then
  ACC_STATUS=$(python3 - <<'PY' "$ACCEPTANCE_REPORT_PATH"
import json, sys
try:
    d = json.load(open(sys.argv[1], "r", encoding="utf-8"))
    print(d.get("status", "UNKNOWN"))
except Exception:
    print("UNKNOWN")
PY
)
  ACC_GATE=$(python3 - <<'PY' "$ACCEPTANCE_REPORT_PATH"
import json, sys
try:
    d = json.load(open(sys.argv[1], "r", encoding="utf-8"))
    print(str(bool(d.get("gate_passed", False))).lower())
except Exception:
    print("false")
PY
)
  ACC_PRIMARY=$(python3 - <<'PY' "$ACCEPTANCE_REPORT_PATH"
import json, sys
try:
    d = json.load(open(sys.argv[1], "r", encoding="utf-8"))
    p = d.get("primary_failure", {}) or {}
    name = p.get("name", "unknown")
    reason = p.get("reason", "unknown")
    print(f"{name}:{reason}")
except Exception:
    print("parse_error:acceptance_report")
PY
)
fi

echo "[delivery-gate] acceptance_status=${ACC_STATUS} gate_passed=${ACC_GATE} rc=${ACC_RC}"
if [[ "$ACC_GATE" != "true" ]]; then
  if [[ "$ACCEPTANCE_POLICY" == "prod" ]]; then
    echo "[delivery-gate] CODE16_ROOT_CAUSE=${ACC_PRIMARY}" >&2
    echo "❌ [FAIL] Acceptance quality gate failed under prod policy." >&2
    exit 16
  fi
  if [[ "$ACC_STATUS" == "UNVERIFIED_COLD_START" ]]; then
    echo "⚠️ [BYPASS] Cold start in dev policy, proceeding with integrity-verified delivery."
  else
    echo "[delivery-gate] CODE16_ROOT_CAUSE=${ACC_PRIMARY}" >&2
    echo "❌ [FAIL] Acceptance quality gate failed (dev policy does not bypass non-cold-start failures)." >&2
    exit 16
  fi
fi

# --- STEP 9: Final Receipt & Lineage Append ---
echo "== Step 9: Receipt & Final Integrity =="

python3 - <<'PY' "$RECEIPT_PATH" "$EVIDENCE_PATH" "$ACCEPTANCE_REPORT_PATH" "$ACCEPTANCE_POLICY" "$ACC_RC" "$ACC_STATUS" "$ACC_GATE" "$ACC_PRIMARY"
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

receipt_path = Path(sys.argv[1])
evidence_path = Path(sys.argv[2])
acceptance_report = Path(sys.argv[3])
acceptance_policy = sys.argv[4]
acceptance_exit_code = int(sys.argv[5])
acceptance_status = sys.argv[6]
acceptance_gate = sys.argv[7].lower() == "true"
acceptance_primary = sys.argv[8]

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
        {"name": "report_integrity", "exit_code": 0, "command": "verify_report_claims.py"},
        {"name": "acceptance", "exit_code": acceptance_exit_code, "command": "acceptance-check"}
    ],
    "artifacts": {
        "evidence": {"path": str(evidence_path), "sha256": sha256(evidence_path)},
        "baseline": {"path": ".nexus/reports/baseline/baseline_manifest.json", "sha256": sha256(Path(".nexus/reports/baseline/baseline_manifest.json"))},
        "acceptance": {"path": str(acceptance_report), "sha256": sha256(acceptance_report)} if acceptance_report.exists() else {"path": str(acceptance_report), "sha256": None}
    },
    "acceptance_policy": acceptance_policy,
    "acceptance_result": {
        "status": acceptance_status,
        "gate_passed": acceptance_gate,
        "primary_cause": acceptance_primary,
    },
    "delivery_gate_passed": True
}
receipt_path.parent.mkdir(parents=True, exist_ok=True)
receipt_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY

echo "[delivery-gate] appending lineage node..."
python3 scripts/ops/append_lineage.py "delivery_gate_receipt" "$(cat $RECEIPT_PATH)"

echo "[delivery-gate] PASS"
