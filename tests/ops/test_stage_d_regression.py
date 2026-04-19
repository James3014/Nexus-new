import subprocess
import json
import os
from pathlib import Path

def test_stage_d():
    print("🧪 Running Stage D Validation...")
    
    baseline_file = Path(".nexus/reports/baseline/baseline_manifest.json")
    lineage_path = Path(".nexus/reports/lineage_chain.jsonl")
    acc_report_path = Path(".nexus/reports/acceptance_check.json")
    
    # Backup
    old_lineage = lineage_path.read_text() if lineage_path.exists() else None
    
    try:
        # Set baseline
        baseline_file.write_text(json.dumps({
            "version": "1.0.0",
            "generated_by_sha": "test",
            "metrics": {"success_rate_threshold": 0.8}
        }))

        # 1. Regression Case: rate 0.5 < 0.8
        print("Case 1: Regression Detected (0.5 < 0.8)")
        acc_report_path.write_text(json.dumps({
            "status": "PASS",
            "metrics": {"auto_repair_success_rate": 50.0}
        }))
        # Append a receipt that points to this report
        subprocess.run(["python3", "scripts/ops/append_lineage.py", "delivery_gate_receipt", 
                        json.dumps({"acceptance_report_path": str(acc_report_path), "head": "fail-sha"})], check=True)
        
        res = subprocess.run(["python3", "scripts/ops/diagnose_regression.py"], capture_output=True, text=True)
        assert res.returncode == 2
        assert "regression detected" in res.stdout.lower()

        # 2. Success Case: rate 0.9 >= 0.8
        print("Case 2: No Regression (0.9 >= 0.8)")
        # Clear lineage for clean test
        lineage_path.unlink()
        acc_report_path.write_text(json.dumps({
            "status": "PASS",
            "metrics": {"auto_repair_success_rate": 90.0}
        }))
        subprocess.run(["python3", "scripts/ops/append_lineage.py", "delivery_gate_receipt", 
                        json.dumps({"acceptance_report_path": str(acc_report_path), "head": "pass-sha"})], check=True)
        
        res = subprocess.run(["python3", "scripts/ops/diagnose_regression.py"], capture_output=True, text=True)
        assert res.returncode == 0
        assert "no regression detected" in res.stdout.lower()

        print("✅ Stage D Validation PASS")

    finally:
        if old_lineage:
            lineage_path.write_text(old_lineage)
        else:
            if lineage_path.exists(): lineage_path.unlink()

if __name__ == "__main__":
    test_stage_d()
