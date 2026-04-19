#!/usr/bin/env python3
import json
import subprocess
import os
import shutil
import sys
from pathlib import Path

# Use Absolute Paths to avoid CWD confusion
CWD = Path.cwd().resolve()
RESULTS_PATH = CWD / ".nexus/reports/qualification_summary.json"
EVIDENCE_PATH = CWD / ".nexus/reports/hallucination_evidence.json"
LINEAGE_PATH = CWD / ".nexus/reports/lineage_chain.jsonl"
ACC_REPORT_PATH = CWD / ".nexus/reports/acceptance_check.json"
BASELINE_PATH = CWD / ".nexus/reports/baseline/baseline_manifest.json"
METRICS_DIR = CWD / ".nexus/metrics"

def setup_env():
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps({
        "version": "1.0.0",
        "generated_by_sha": "suite",
        "metrics": {"success_rate_threshold": 0.8}
    }))
    
    ignore_conf = CWD / ".nexus/config/delivery_gate_allow_dirty.json"
    ignore_conf.parent.mkdir(parents=True, exist_ok=True)
    ignore_conf.write_text(json.dumps({
        "ignore_dirty_paths": [".nexus/reports/", ".nexus/metrics/", "tests/ops/"]
    }))
    subprocess.run([sys.executable, "scripts/ops/seal_governance.py"], capture_output=True)

def run_case(name, setup_fn, *, acceptance_policy="dev"):
    print(f"🏃 Running Case: {name}...")
    setup_fn()
    # Explicitly run from CWD
    env = os.environ.copy()
    env["NEXUS_ACCEPTANCE_POLICY"] = acceptance_policy
    res = subprocess.run(
        ["bash", "scripts/ops/nexus_delivery_gate.sh"],
        capture_output=True,
        text=True,
        cwd=str(CWD),
        env=env,
    )
    passed = (res.returncode == 0)
    print(f"  - Result: {'PASS' if passed else 'FAIL'} (Code: {res.returncode})")
    if not passed:
        print(f"    STDOUT: {res.stdout[:200]}...")
        print(f"    STDERR: {res.stderr[:200]}...")
    return {"name": name, "passed": passed, "exit_code": res.returncode}

def main():
    setup_env()
    results = []

    def clear():
        if LINEAGE_PATH.exists(): LINEAGE_PATH.unlink()
        subprocess.run([sys.executable, "scripts/ops/seal_governance.py"], capture_output=True)

    def ok_evidence():
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(json.dumps({
            "final_response": "The task is ready for review.",
            "evidence_bundle": {"test_artifacts": [{"aggregates": {"success_rate": 1.0}}]}
        }))
        
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        
        # 1. skill_outcome_events.jsonl
        events = []
        for _ in range(15):
            events.append({
                "source": "pipeline.crystallize",
                "pass": True,
                "timestamp": "2026-04-19T10:00:00Z",
                "pattern_reuse": 1.0,
                "next_run_hit": 1.0,
                "regression_pass_rate": 100.0,
            })
        for _ in range(10):
            events.append({
                "source": "pipeline.repair",
                "pass": True,
                "timestamp": "2026-04-19T10:00:00Z",
                "retry_count": 0,
                "regression_verified": True,
                "regression_pass_rate": 100.0,
            })
        for _ in range(10):
            events.append({
                "source": "pipeline.ucc",
                "pass": True,
                "timestamp": "2026-04-19T10:00:00Z",
                "truth_aligned": True,
                "reach_success": True,
                "regression_pass_rate": 100.0,
            })
        (METRICS_DIR / "skill_outcome_events.jsonl").write_text("\n".join([json.dumps(e) for e in events]) + "\n")
        
        # 2. skills_optimization_runs.jsonl
        opt_runs = []
        for _ in range(5):
            opt_runs.append({"success": True, "timestamp": "2026-04-19T10:00:00Z"})
        (METRICS_DIR / "skills_optimization_runs.jsonl").write_text("\n".join([json.dumps(r) for r in opt_runs]) + "\n")

    # --- Normal Cases ---
    for i in range(1, 6):
        def setup():
            clear()
            ok_evidence()
        results.append(run_case(f"Normal_{i}", setup, acceptance_policy="dev"))

    # --- Adversarial Cases ---
    def setup_a1():
        clear()
        ok_evidence()
        with open("scripts/ops/diagnose_regression.py", "a") as f: f.write("# DRIFT\n")
    results.append(run_case("Adv_Drift", setup_a1, acceptance_policy="dev"))
    subprocess.run(["git", "checkout", "scripts/ops/diagnose_regression.py"], capture_output=True)

    def setup_a2():
        clear()
        ok_evidence()
        subprocess.run([sys.executable, "scripts/ops/append_lineage.py", "test", "{}"], capture_output=True)
        with open(LINEAGE_PATH, "a") as f: f.write("TAMPERED\n")
    results.append(run_case("Adv_Lineage", setup_a2, acceptance_policy="dev"))

    def setup_a3():
        clear()
        EVIDENCE_PATH.write_text(json.dumps({"evidence_bundle": {"test_artifacts": []}}))
    results.append(run_case("Adv_NoEvidence", setup_a3, acceptance_policy="dev"))

    def setup_a4():
        clear()
        ok_evidence()
        # Trigger regression by injecting failures to the outcome file
        events = [{"source": "pipeline.repair", "pass": False, "timestamp": "2026-04-19T10:00:00Z"}] * 10
        (METRICS_DIR / "skill_outcome_events.jsonl").write_text("\n".join([json.dumps(e) for e in events]) + "\n")
        # Add a lineage node to trigger the check
        subprocess.run([sys.executable, "scripts/ops/append_lineage.py", "delivery_gate_receipt", json.dumps({"acceptance_report_path": str(ACC_REPORT_PATH)})], capture_output=True)
    results.append(run_case("Adv_Regression", setup_a4, acceptance_policy="dev"))

    def setup_a5():
        clear()
        ok_evidence()
        (METRICS_DIR / "skill_outcome_events.jsonl").write_text("") # Clear to fail acceptance
    results.append(run_case("Adv_AcceptanceFail", setup_a5, acceptance_policy="prod"))

    summary = {
        "total": len(results),
        "normal_pass_rate": sum(1 for r in results if r["passed"] and "Normal" in r["name"]) / 5.0,
        "adversarial_block_rate": sum(1 for r in results if not r["passed"] and "Adv" in r["name"]) / 5.0,
        "results": results
    }
    print(f"\n📊 Qualification Summary: Normal={summary['normal_pass_rate']:.0%}, Adv={summary['adversarial_block_rate']:.0%}")
    RESULTS_PATH.write_text(json.dumps(summary, indent=2))
    sys.exit(0 if summary['normal_pass_rate'] >= 0.8 and summary['adversarial_block_rate'] >= 1.0 else 1)

if __name__ == "__main__":
    main()
