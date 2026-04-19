import subprocess
import json
import os
from pathlib import Path

def test_stage_a():
    print("🧪 Running Stage A Validation...")
    
    baseline_dir = Path(".nexus/reports/baseline")
    baseline_file = baseline_dir / "baseline_manifest.json"
    
    # Backup original
    original_content = baseline_file.read_text()
    
    try:
        # 1. Test Missing Version/SHA
        print("Case 1: Invalid Schema (Missing fields)")
        baseline_file.write_text(json.dumps({"old_field": "test"}))
        res = subprocess.run(["python3", "scripts/ops/diagnose_regression.py", ".nexus/reports/acceptance_check.json"], capture_output=True, text=True)
        assert res.returncode != 0
        assert "missing required fields" in res.stdout.lower() or "missing required fields" in res.stderr.lower()
        
        res_verify = subprocess.run(["python3", "scripts/ops/verify_report_claims.py", "--json"], capture_output=True, text=True)
        report = json.loads(res_verify.stdout)
        baseline_check = next(c for c in report["checks"] if c["name"] == "baseline_manifest")
        assert baseline_check["passed"] is False
        assert baseline_check["detail"]["error"] == "missing_schema_fields"
        
        # 2. Test Missing File
        print("Case 2: Missing Baseline File")
        baseline_file.unlink()
        res = subprocess.run(["python3", "scripts/ops/diagnose_regression.py", ".nexus/reports/acceptance_check.json"], capture_output=True, text=True)
        assert res.returncode != 0
        assert "missing baseline manifest" in res.stdout.lower()
        
        res_verify = subprocess.run(["python3", "scripts/ops/verify_report_claims.py", "--json"], capture_output=True, text=True)
        report = json.loads(res_verify.stdout)
        baseline_check = next(c for c in report["checks"] if c["name"] == "baseline_manifest")
        assert baseline_check["passed"] is False
        assert baseline_check["detail"]["exists"] is False

        # 3. Test Success Path
        print("Case 3: Success Path")
        baseline_file.write_text(original_content)
        res_verify = subprocess.run(["python3", "scripts/ops/verify_report_claims.py", "--json"], capture_output=True, text=True)
        report = json.loads(res_verify.stdout)
        baseline_check = next(c for c in report["checks"] if c["name"] == "baseline_manifest")
        assert baseline_check["passed"] is True
        
        print("✅ Stage A Validation PASS")

    finally:
        baseline_file.write_text(original_content)

if __name__ == "__main__":
    test_stage_a()
