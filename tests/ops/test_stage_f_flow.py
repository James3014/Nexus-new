import subprocess
import json
import os
from pathlib import Path

def test_stage_f():
    print("🧪 Running Stage F Validation...")
    
    evidence_path = Path(".nexus/reports/hallucination_evidence.json")
    baseline_path = Path(".nexus/reports/baseline/baseline_manifest.json")
    
    # 確保基本環境
    evidence_path.write_text(json.dumps({
        "final_response": "The task is ready for review.",
        "evidence_bundle": {"test_artifacts": [{"aggregates": {"success_rate": 1.0}}]}
    }))
    
    try:
        # 1. Test Drift Failure (Exit 11)
        print("Case 1: Drift Failure")
        subprocess.run(["python3", "scripts/ops/seal_governance.py"], check=True)
        # Tamper a sealed file
        target = Path("scripts/ops/diagnose_regression.py")
        original = target.read_text()
        target.write_text(original + "\n# DRIFT\n")
        
        res = subprocess.run(
            ["bash", "scripts/ops/nexus_delivery_gate.sh"],
            capture_output=True,
            text=True,
            env={**os.environ, "NEXUS_ACCEPTANCE_POLICY": "dev"},
        )
        assert res.returncode == 11
        assert "governance drift detected" in res.stderr.lower()
        target.write_text(original) # Restore
        
        # 2. Test Lineage Failure (Exit 12)
        print("Case 2: Lineage Failure")
        lineage_path = Path(".nexus/reports/lineage_chain.jsonl")
        lineage_path.write_text("INVALID_JSON\n")
        res = subprocess.run(
            ["bash", "scripts/ops/nexus_delivery_gate.sh"],
            capture_output=True,
            text=True,
            env={**os.environ, "NEXUS_ACCEPTANCE_POLICY": "dev"},
        )
        assert res.returncode == 12
        assert "lineage chain broken" in res.stderr.lower()
        if lineage_path.exists(): lineage_path.unlink() # Restore

        # 3. Test Success Flow
        print("Case 3: Success Flow")
        # Ensure all dependencies are green
        subprocess.run(["python3", "scripts/ops/seal_governance.py"], check=True)
        
        # Simulate real metrics for acceptance-check to pass
        metrics_dir = Path(".nexus/metrics")
        metrics_dir.mkdir(parents=True, exist_ok=True)
        events = []
        for _ in range(10):
            events.append(json.dumps({"source": "pipeline.crystallize", "pass": True, "timestamp": "2026-04-19T10:00:00Z", "pattern_reuse": 1.0, "next_run_hit": 1.0, "regression_pass_rate": 100.0}))
        for _ in range(5):
            events.append(json.dumps({"source": "pipeline.repair", "pass": True, "timestamp": "2026-04-19T10:00:00Z", "retry_count": 0, "regression_pass_rate": 100.0, "regression_verified": True}))
        for _ in range(5):
            events.append(json.dumps({"source": "pipeline.ucc", "pass": True, "timestamp": "2026-04-19T10:00:00Z", "truth_aligned": True, "regression_pass_rate": 100.0}))
        (metrics_dir / "skill_outcome_events.jsonl").write_text("\n".join(events) + "\n")
        
        # Also need skill_optimization_runs.jsonl
        (metrics_dir / "skills_optimization_runs.jsonl").write_text(json.dumps({"success": True, "timestamp": "2026-04-19T10:00:00Z"}) + "\n")

        res = subprocess.run(
            ["bash", "scripts/ops/nexus_delivery_gate.sh"],
            capture_output=True,
            text=True,
            env={**os.environ, "NEXUS_ACCEPTANCE_POLICY": "dev"},
        )
        # Full Pass expected now
        if res.returncode != 0:
            print(f"  - Unexpected Exit Code: {res.returncode}")
            print(f"  - STDERR: {res.stderr}")
        assert res.returncode == 0
        receipt = json.loads(Path(".nexus/reports/delivery_gate.json").read_text())
        assert receipt["delivery_gate_passed"] is True

        # 4. Test strict acceptance fail with explainable Code 16
        print("Case 4: Strict Acceptance Fail (Code 16 with root cause)")
        (metrics_dir / "skill_outcome_events.jsonl").write_text("")
        res = subprocess.run(
            ["bash", "scripts/ops/nexus_delivery_gate.sh"],
            capture_output=True,
            text=True,
            env={**os.environ, "NEXUS_ACCEPTANCE_POLICY": "prod"},
        )
        assert res.returncode == 16
        assert "code16_root_cause=" in res.stderr.lower()

        print("✅ Stage F Validation PASS")

    finally:
        pass

if __name__ == "__main__":
    test_stage_f()
