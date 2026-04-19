#!/usr/bin/env python3
import json
import subprocess
import os
import shutil
import sys
from pathlib import Path

RESULTS_PATH = Path(".nexus/reports/qualification_summary.json")
EVIDENCE_PATH = Path(".nexus/reports/hallucination_evidence.json")
LINEAGE_PATH = Path(".nexus/reports/lineage_chain.jsonl")
ACC_REPORT_PATH = Path(".nexus/reports/acceptance_check.json")
BASELINE_PATH = Path(".nexus/reports/baseline/baseline_manifest.json")

def setup_env():
    # Ensure baseline is set
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps({
        "version": "1.0.0",
        "generated_by_sha": "suite",
        "metrics": {"success_rate_threshold": 0.8}
    }))
    # Ensure seal is valid
    subprocess.run(["python3", "scripts/ops/seal_governance.py"], capture_output=True)

def run_case(name, setup_fn):
    print(f"🏃 Running Case: {name}...")
    setup_fn()
    res = subprocess.run(["bash", "scripts/ops/nexus_delivery_gate.sh"], capture_output=True, text=True)
    passed = (res.returncode == 0)
    print(f"  - Result: {'PASS' if passed else 'FAIL'} (Code: {res.returncode})")
    return {"name": name, "passed": passed, "exit_code": res.returncode}

def main():
    setup_env()
    results = []

    def clear():
        if LINEAGE_PATH.exists(): LINEAGE_PATH.unlink()
        if EVIDENCE_PATH.exists(): EVIDENCE_PATH.unlink()
        if ACC_REPORT_PATH.exists(): ACC_REPORT_PATH.unlink()
        subprocess.run(["python3", "scripts/ops/seal_governance.py"], capture_output=True)

    def ok_evidence():
        EVIDENCE_PATH.write_text(json.dumps({
            "final_response": "Ready",
            "evidence_bundle": {"test_artifacts": [{"aggregates": {"success_rate": 1.0}}]}
        }))
        ACC_REPORT_PATH.write_text(json.dumps({"status": "PASS", "gate_passed": True, "metrics": {"auto_repair_success_rate": 100.0}}))

    # --- Normal Cases ---
    for i in range(1, 6):
        def setup():
            clear()
            ok_evidence()
        results.append(run_case(f"Normal_{i}", setup))

    # --- Adversarial Cases ---
    
    # A1: Drift
    def setup_a1():
        clear()
        ok_evidence()
        with open("scripts/ops/diagnose_regression.py", "a") as f:
            f.write("# DRIFT\n")
    results.append(run_case("Adv_Drift", setup_a1))
    # Restore drift
    subprocess.run(["git", "checkout", "scripts/ops/diagnose_regression.py"], capture_output=True)

    # A2: Lineage
    def setup_a2():
        clear()
        ok_evidence()
        subprocess.run(["python3", "scripts/ops/append_lineage.py", "test", "{}"], capture_output=True)
        with open(LINEAGE_PATH, "a") as f:
            f.write("TAMPERED\n")
    results.append(run_case("Adv_Lineage", setup_a2))

    # A3: Empty Evidence
    def setup_a3():
        clear()
        EVIDENCE_PATH.write_text(json.dumps({"evidence_bundle": {"test_artifacts": []}}))
    results.append(run_case("Adv_NoEvidence", setup_a3))

    # A4: Regression
    def setup_a4():
        clear()
        EVIDENCE_PATH.write_text(json.dumps({
            "final_response": "Ready",
            "evidence_bundle": {"test_artifacts": [{"aggregates": {"success_rate": 1.0}}]}
        }))
        ACC_REPORT_PATH.write_text(json.dumps({"status": "PASS", "gate_passed": True, "metrics": {"auto_repair_success_rate": 50.0}}))
        # Need a previous receipt in lineage to trigger regression check in some logic, 
        # but our current script checks the LATEST lineage nodes.
        subprocess.run(["python3", "scripts/ops/append_lineage.py", "delivery_gate_receipt", 
                        json.dumps({"acceptance_report_path": str(ACC_REPORT_PATH)})], capture_output=True)
    results.append(run_case("Adv_Regression", setup_a4))

    # A5: Acceptance Fail
    def setup_a5():
        clear()
        ok_evidence()
        # Clear metrics to trigger failure
        metrics_path = Path(".nexus/metrics/skill_outcome_events.jsonl")
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text("") 
    results.append(run_case("Adv_AcceptanceFail", setup_a5))

    # Summary
    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "normal_pass_rate": sum(1 for r in results if r["passed"] and "Normal" in r["name"]) / 5.0,
        "adversarial_block_rate": sum(1 for r in results if not r["passed"] and "Adv" in r["name"]) / 5.0,
        "results": results
    }

    print("\n" + "="*30)
    print(f"📊 Qualification Summary:")
    print(f"  Normal Pass Rate: {summary['normal_pass_rate']:.0%}")
    print(f"  Adv Block Rate: {summary['adversarial_block_rate']:.0%}")
    print("="*30)

    RESULTS_PATH.write_text(json.dumps(summary, indent=2))
    
    # Validation Thresholds
    success = True
    if summary['normal_pass_rate'] < 0.8: success = False
    if summary['adversarial_block_rate'] < 1.0: success = False
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
