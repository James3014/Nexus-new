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
if ! uv run python3 -m pytest -q tests/nexus/orchestrator; then
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
python3 scripts/ops/write_delivery_receipt.py \
  --receipt-path "$RECEIPT_PATH" \
  --evidence-path "$EVIDENCE_PATH" \
  --baseline-path "$BASELINE_PATH" \
  --acceptance-report "$ACCEPTANCE_REPORT_PATH" \
  --acceptance-policy "$ACCEPTANCE_POLICY" \
  --acceptance-exit-code "$ACC_RC" \
  --acceptance-status "$ACC_STATUS" \
  --acceptance-gate "$ACC_GATE" \
  --acceptance-primary "$ACC_PRIMARY"

echo "[delivery-gate] appending lineage node..."
python3 scripts/ops/append_lineage.py "delivery_gate_receipt" "$(cat $RECEIPT_PATH)"

echo "[delivery-gate] PASS"
